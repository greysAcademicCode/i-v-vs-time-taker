# -*- coding: utf-8 -*-
"""
Created on Wed Mar  6 18:09:28 2013

here we have a threadsafe gpib interface class (actually should work with any visa connection)

pyvisa must be installed and working before this can be used
a "working" pyvisa requires a visa instrument driver being installed and working
i've tested this with visa drivers for gpib bus interface adapters from national instruments and keithley

this class has two modes of operation: queue mode and non-queue mode
select between them during init
use the queue mode for safe interaction with a gpib instrument when calling from multiple threads
use the non-queue mode if calling from a clientwith only one thread
in queue mode:
the user will instantiate the class and then interact with the task_queue and done_queue objects which carry instructions to a thread-save visa object
this is done by entering the visa function name and the arguments into the task_queue object and retrieving results from done_queue later:
from pygrey.gpib import gpib
k.task_queue.put(('ask',('*idn?',)))
print k.done_queue.get()
k.task_queue.put('STOP') <-- this cleans things up properly
in non-queue mode:
the user will interact with the visa v object created during initialization
example:
from pygrey.gpib import gpib
k = gpib('GPIB0::23')
print k.v.ask(':read?')

see the pyvisa documentation on how to interact with a visa object

@author: grey
"""

import visa
from multiprocessing import Process, Queue

class gpib:
    delay = 0#command transmit delay
    values_format = visa.single | visa.big_endian #this is now a keithley 2400 does binary transfers
    chunk_size = 102400 #need a slightly bigger transfer buffer than default to be able to transfer a full sample buffer (2500 samples) from a keithley 2400 in one shot
    def __init__(self,locationString=None,timeout=30,useQueues=False):
        self.locationString = locationString
        self.timeout = timeout
        self.useQueues = useQueues

        if self.locationString is not None:
            if self.useQueues: #queue mode
                #build the queues
                self.task_queue = Queue()
                self.done_queue = Queue()
                #kickoff the worker process
                self.p = Process(target=self._worker, args=(self.task_queue, self.done_queue))
                self.p.start()
            else:#non-queue mode
                self.v = visa.instrument(self.locationString,timeout=self.timeout,chunk_size=self.chunk_size,delay=self.delay,values_format=self.values_format)

    def __del__(self):
        if self.useQueues:
            if self.p.is_alive():
                self.task_queue.put('STOP')
            self.p.join()
            self.task_queue.close()
            self.done_queue.close()
            self.task_queue.join_thread()
            self.done_queue.join_thread()
        else:
            if hasattr(self,'v'):
                self.v.close()

    def _worker(self, inputQ, outputQ):
        #local, threadsafe instrument object created here
        v = visa.instrument(self.locationString,timeout=self.timeout,chunk_size=self.chunk_size,delay=self.delay,values_format=self.values_format)
        for func, args in iter(inputQ.get, 'STOP'):#queue processing going on here
            try:
                toCall = getattr(v,func)
                ret = toCall(*args)#visa function call occurs here
            except:
                ret = None
            if ret: #don't put None outputs into output queue
                outputQ.put(ret)
        print "queue worker closed properly"
        v.close()
        inputQ.close()
        outputQ.close()

    #make queue'd and non-queued writes look the same to the client
    def write(self,string):
        if self.useQueues:
            self.task_queue.put(('write',(string,)))
        else:
            self.v.write(string)

    #controls remote enable line
    def controlRen(self,mode):
        visa.Gpib()._vpp43.gpib_control_ren(mode)

    def clearInterface(self):
        visa.Gpib().send_ifc()

    def findInstruments(self):
        return visa.get_instruments_list()    