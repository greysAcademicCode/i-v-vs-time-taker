# -*- coding: utf-8 -*-
"""
This is a program to control a keithley 2400 sourcemeter.
It allows for high frequency (~150Hz at present) sampling during I-V sourcemeasurements to gain insight into some device dynamics
@author: grey
"""
#TODO: change to user input of voltage dwell time
import os, sys, inspect

try:
    from gpib import gpib
    gotGPIB = True
except:
    gotGPIB = False
    print "Could not import GPIB"

import pprint
pp = pprint.PrettyPrinter(indent=4)
import math
from PyQt4.QtCore import QString, QThread, pyqtSignal, QTimer, QSettings, QTemporaryFile, QIODevice
from PyQt4.QtGui import QApplication, QDialog, QMainWindow, QFileDialog, QMessageBox
from ivSweeperUI import Ui_IVSweeper
from collections import OrderedDict

from scipy import optimize

import numpy as np
import time
import struct

#read one measurement value from queue
def qBinRead(q):

    nElements = 4 #this needs to match the :format:elements setting in the device or else you're gonna have a bad time
    formatString = '>{0}f'.format(nElements)
    #this is raw binary data form the instrument
    qItem = q.get()

    #here we unpack the binary data from the instrument, the first two bytes are the header, '#0' we ignore those.
    #Next we have each of our four measurement values in IEEE-754 single precision data format (32 data bits)
    #1st is time 2nd is voltage, 3rd is current, 4th is the status info 
    data = (struct.unpack(formatString,qItem[2:nElements*4+2]))

    return (data)



#here we have the thread that generates the commands that advance the source value during the sweep
class sweepThread(QThread):
    updateProgress = pyqtSignal(float)
    sweepComplete = pyqtSignal() #indicates sweep is complete

    def __init__(self, q, parent=None):
        QThread.__init__(self, parent)

        self.q = q #gpib command queue

        #self.prematureTermination = False

    def updateVariables(self,dt,sweepPoints,sourceName):
        self.dt = dt
        self.sweepPoints = sweepPoints
        self.sourceName = sourceName

    #def earlyKill(self):
    #    self.prematureTermination = True

    def run(self):
        i = float(0)
        nPoints = len(self.sweepPoints)
        self.updateProgress.emit(0)
        #autozero once before the sweep to prevent zero point drift
        self.q.put(('write',(':system:azero once',)))
        for point in self.sweepPoints:
            i = i + 1
            self.q.put(('write',(':source:' + str(self.sourceName) + ' {0:.4f}'.format(point),)))
            time.sleep(self.dt)
            self.updateProgress.emit(i/nPoints*100)
            #if self.prematureTermination: #sweep termination only has time resolution of dt, oh well
            #    break
        self.sweepComplete.emit()
        #self.prematureTermination = False

#here we have the thread that generates the measurement request commands
class measureThread(QThread): 
    measureDone = pyqtSignal(int) #signal how many data points need to be collected
    def __init__(self, q, parent=None):
        QThread.__init__(self, parent)

        self.q = q #gpib command queue

        self.finishUpNow = False

    def timeToDie(self):
        self.finishUpNow = True

    def run(self):
        dataPoints = 1
        self.q.put(('read_raw',()))
        while not self.finishUpNow: #keep spamming read requests unless it's time to die (sweep is complete)
            time.sleep(0.001)#only do the queue check only every millisecond to prevent pegging the CPU in this loop
            if self.q.qsize()<5: #keep ~5 measurement requests in the task queue at all times, this is a small enough number to keep things snappy on termination, and large enough to ensure a measurement request is always queued
                self.q.put(('read',()))#TODO: is read_raw better here?
                dataPoints = dataPoints + 1
        self.finishUpNow = False
        self.measureDone.emit(dataPoints) #here we signal how many data points will need to be collected

class postProcessThread(QThread):
    sweepUp = True
    area = ''
    tempFile = ''
    saveTime = False
    savePath = ''
    readyToProcess = pyqtSignal() #signal when we're ready to post process
    postProcessingComplete = pyqtSignal() #signal when we're ready to post process
    debug = True
    rawData = []
    def __init__(self, parent=None):
        QThread.__init__(self, parent)

    def acceptNewData(self,data):
        self.rawData = data
        self.readyToProcess.emit()

    def run(self):
        self.tempFile.open()
        self.tempFile.close()
        tempFileName = str(self.tempFile.fileName())
        v = self.rawData[:,0]
        i = self.rawData[:,1]
        t = self.rawData[:,2]
        pmaxRaw = np.max(v*i)
        t = t - t[0] #zero time offset
        #print t[-1]
        diffs = np.diff(t)
        meandt = np.mean(diffs)
        maxdt = np.max(diffs)
        mindt = np.min(diffs)
        
        
        hdr = 'Area = {0:s} [cm^2]\n'.format(self.area)
        hdr = hdr + 'I&V vs t = {0:b}\n'.format(self.saveTime)
        hdr = hdr + 'sweepUp = {0:b}\n'.format(self.sweepUp)
        if not self.saveTime:#only save iv data
            hdr = hdr+'Voltage [V],Current [A]'
            self.rawData = self.rawData[:,(0,1)]
        else:
            hdr = hdr+'Voltage [V],Current [A],Time[s],Status'
        np.savetxt(tempFileName, self.rawData, delimiter=",",header=hdr)
        saveDestination = self.savePath+'_'+str(int(time.time()))+'.csv'
        self.tempFile.copy(saveDestination)
        self.tempFile.remove()
        
        parameters = {'00_nSamples': len(t), \
                      '01_pMaxRaw[mW]': pmaxRaw*1000, \
                      '02_worstSpeed[Hz]': 1/maxdt, \
                      '03_worstSpeed[ms]':  maxdt*1000, \
                      '04_bestSpeed[Hz]': 1/mindt, \
                      '05_bestSpeed[ms]':  mindt*1000, \
                      '06_meanSpeed[Hz]': 1/meandt, \
                      '07_meanSpeed[ms]':  meandt*1000}
        if self.debug:
            pp.pprint(parameters)
        self.rawData = []
        self.postProcessingComplete.emit()
        
        
class ivDataThread(QThread):
    rawData = []
    postData = pyqtSignal(np.ndarray) #send away the data collected here
    def __init__(self, taskQ, doneQ, parent=None):
        QThread.__init__(self, parent)
        self.taskQ = taskQ#gpib done queue
        self.doneQ = doneQ#gpib done queue
    def run(self):
        self.taskQ.put(('read_values',()))
        rawData = np.array(self.doneQ.get())
        self.postData.emit(rawData.reshape((-1,4)))

class readRealTimeDataThread(QThread):
    rawData = []
    pointsToCollect = np.inf
    postData = pyqtSignal(np.ndarray) #send away the data collected here
    def __init__(self, q, parent=None):
        QThread.__init__(self, parent)
        self.q = q#gpib done queue
    def updatePoints(self,nPoints):
        self.pointsToCollect = nPoints
    def run(self):
        self.rawData = []
        collected = 0
        while True:
            newData = qBinRead(self.q)
            self.rawData.append(newData)
            collected = collected + 1
            if collected >= self.pointsToCollect:
                break

        self.pointsToCollect = np.inf
        if (len(self.rawData) >2):
            arrayData = np.array(self.rawData)
            arrayData = arrayData[arrayData[:,2].argsort()]
            self.postData.emit(arrayData)
            
#here we have the thread that searches the bus for instruments
class instrumentDetectThread(QThread):
    foundInstruments = pyqtSignal(list) #signal containing list instruments we've found
    def __init__(self, parent=None):
        QThread.__init__(self, parent)

    def run(self):
        try:
            resourceNames = gpib().findInstruments()
        except:
            resourceNames = ["None found"]
        self.foundInstruments.emit(resourceNames)

#this is the main gui window
class MainWindow(QMainWindow):
    sweepVaribles = pyqtSignal(float,np.ndarray,str)
    #killSweepNow = pyqtSignal()
    sweepUp = True
    userWantsOn = False #the user wants the output off
    def __init__(self):
        QMainWindow.__init__(self)
        
        self.instrumentDetectThread = instrumentDetectThread()
        self.instrumentDetectThread.foundInstruments.connect(self.catchList)

        self.settings = QSettings("greyltc", "ivSweeper")   

        #how long status messages show for
        self.messageDuration = 1000#ms

        #variables to keep track of what we're sourcing/sensing
        self.source = "voltage"
        self.sense = "current"
        self.senseUnit = 'A'
        self.sourceUnit = 'V'

        #variable to keep track of if a sweep is ongoing
        self.sweeping = False

        # Set up the user interface from Designer.
        self.ui = Ui_IVSweeper()
        self.ui.setupUi(self)
        
        if self.settings.contains('lastFolder'):
            self.ui.dirEdit.setText(self.settings.value('lastFolder').toString())          

        #connect signals generated by gui elements to proper functions        
        self.ui.sweepButton.clicked.connect(self.manageSweep)
        self.ui.shutterButton.clicked.connect(self.handleShutter)
        self.ui.frontRadio.toggled.connect(self.setTerminals)
        self.ui.sourceVRadio.toggled.connect(self.setMode)
        self.ui.twowireRadio.toggled.connect(self.setWires)
        self.ui.zeroCheck.toggled.connect(self.setZero)
        self.ui.speedCombo.currentIndexChanged.connect(self.setSpeed)
        self.ui.averageSpin.valueChanged.connect(self.setAverage)
        self.ui.complianceSpin.valueChanged.connect(self.setCompliance)
        self.ui.startSpin.valueChanged.connect(self.setStart)
        self.ui.endSpin.valueChanged.connect(self.setSourceRange)
        self.ui.outputCheck.toggled.connect(self.setOutput)
        self.ui.delaySpinBox.valueChanged.connect(self.updateDeltaText)
        self.ui.totalPointsSpin.valueChanged.connect(self.updateDeltaText)
        self.ui.reverseButton.clicked.connect(self.reverseCall)
        self.ui.actionRun_Test_Code.triggered.connect(self.testArea)
        self.ui.instrumentCombo.activated.connect(self.handleICombo)
        self.ui.saveModeCombo.currentIndexChanged.connect(self.handleModeCombo)
        
        self.ui.browseButton.clicked.connect(self.browseButtonCall)
        self.ui.outputCheck.clicked.connect(self.toggleWhatUserWants)

        #TODO: load state here
        #self.restoreState(self.settings.value('guiState').toByteArray())
        
    #this keeps track of clicks on the output/on off box
    def toggleWhatUserWants(self):
        self.userWantsOn = not self.userWantsOn

    def handleModeCombo(self):
        dt = self.ui.delaySpinBox.value()
        if self.ui.saveModeCombo.currentIndex() == 0: #i,v vs t mode
            startValue = float(self.ui.startSpin.value())
            endValue = float(self.ui.endSpin.value())
            span = abs(endValue-startValue)+1
            self.ui.totalPointsSpin.setMaximum(span)
            self.ui.totalPointsSpin.setMinimum(1)

            self.sendCmd(":source:delay 0")
            self.sendCmd(':source:'+self.source+':mode fixed')
            self.sendCmd(':trigger:count 1')
            #fast response and no auto zeroing in i,v vs t mode
            self.ui.speedCombo.setCurrentIndex(0)
            self.ui.zeroCheck.setChecked(False)
        else: #traditional i vs v mode
            #TODO: figure out why this mode is double scanning for 70 points 1 sec delay
            self.ui.totalPointsSpin.setMaximum(2500) #standard sweeps can be at most 2500 points long (keithley limitation)
            self.ui.totalPointsSpin.setMinimum(2)
            self.ui.speedCombo.setCurrentIndex(3)#go slow here
            
            self.sendCmd(":source:delay {0:0.3f}".format(dt))
            self.sendCmd(':source:'+self.source+':mode sweep')
            
            nPoints = float(self.ui.totalPointsSpin.value())
            self.sendCmd(':trigger:count {0:d}'.format(int(nPoints)))
            #high accuracy and auto zeroing in i vs v mode
            self.ui.speedCombo.setCurrentIndex(3)
            self.ui.zeroCheck.setChecked(True)
            
        
        
    def catchList(self,resourceNames):
        for i in range(self.ui.instrumentCombo.count()):
            self.ui.instrumentCombo.removeItem(0)
        self.ui.instrumentCombo.setEnabled(True)
        self.ui.instrumentCombo.insertItem(0,'Select Instrument')
        self.ui.instrumentCombo.insertItem(1,'(Re)Scan for Instruments')
        i = 2
        for instrument in resourceNames:
            self.ui.instrumentCombo.insertItem(i,instrument)
            i = i +1
        self.ui.instrumentCombo.setCurrentIndex(0)  
        
    def handleICombo(self,index):
        #index = self.ui.instrumentCombo.currentIndex()
        thisString = str(self.ui.instrumentCombo.currentText())
        scanString = '(Re)Scan for Instruments'
        selectString = 'Select Instrument'
        noneString = "None found"
        if thisString == scanString:
            self.ui.instrumentCombo.setItemText(index,'Searching...')
            self.ui.instrumentCombo.setEnabled(False)
            self.instrumentDetectThread.start()
        elif (thisString == selectString) or (thisString == noneString):
            pass
        else:
            self.initialConnect(thisString)
            
            

    def browseButtonCall(self):      
        dirName = QFileDialog.getExistingDirectory(directory=self.ui.dirEdit.text())
        self.settings.setValue('lastFolder',dirName)
        self.ui.dirEdit.setText(dirName)

    #return -1 * the power of the device at a given voltage or current
    def invPower(self,request):
        request = request[0]
        
        #TODO: remove this testing current fudge value
        #currentFudge = 0.004;
        currentFudge = 0;
        
        try:
            print request
            self.sendCmd('source:'+self.source+' {0:.3f}'.format(request))
            self.k.task_queue.put(('read_raw',())) #TODO: this should be split to another function
            data = qBinRead(self.k.done_queue)
            return (data[0]*(data[1]-currentFudge))
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration);
            return np.nan


    def handleShutter(self):
        shutterOnValue = '14'
        shutterOffValue = '15'
        self.k.task_queue.put(('ask',(':source2:ttl:actual?',))) #TODO: this should be split to another function
        outStatus = self.k.done_queue.get()
        if outStatus == shutterOnValue:
            self.sendCmd(":source2:ttl " + shutterOffValue)
        else:
            self.sendCmd(":source2:ttl " + shutterOnValue)
    
    #TODO: move this to its own thread
    def maxPowerDwell(self):
        voltageSourceRange = 3 # operate between +/- 3V
        currentSourceRange = 0.1 # operate between +/- 100ma
        if self.sourceUnit == 'V': 
            self.sendCmd(':source:'+self.source+':range {0:.3f}'.format(voltageSourceRange))
            initialGuess = 0.7
        else:
            self.sendCmd(':source:'+self.source+':range {0:.3f}'.format(currentSourceRange))
            initialGuess = 0.01 # no idea if this is right

        dt = self.ui.delaySpinBox.value()
        nPoints = float(self.ui.totalPointsSpin.value())
        
        self.ui.outputCheck.setChecked(True)
        oldSpeedIndex = self.ui.speedCombo.currentIndex()
        self.ui.speedCombo.setCurrentIndex(2)
        
        
        for i in range(int(nPoints)):
            optResults = optimize.minimize(self.invPower,initialGuess,method='COBYLA',tol=1e-4,options={'rhobeg':0.2})
            print optResults.message
            print optResults.status
            answer = float(optResults.x)
            initialGuess = answer
            self.sendCmd(":SYST:KEY 23") #go into local mode for live display update
            print "Optimized! Mpp Voltage: {0:.3f}".format(answer)
            print "Now sleeping for {0:.1f} seconds".format(dt)
            time.sleep(dt)
            self.k.task_queue.put(('read_raw',()))
            data = qBinRead(self.k.done_queue)        
            #vi = (data[0], data[1], data[1]*data[0]*1000/.4*-1)
            print 'Max Power: {0:.3f}% '.format(data[0]*data[1]*1000/float(self.ui.deviceAreaEdit.text()))
        self.ui.outputCheck.setChecked(self.userWantsOn)
        self.ui.speedCombo.setCurrentIndex(oldSpeedIndex)

    def testArea(self):
        print('Running test code now')
        #self.maxPowerDwell()

        #x = np.random.randn(10000)
        #np.hist(x, 100)        

    def closeEvent(self,event):
        #TODO: save state here
        #self.settings.setValue('guiState',self.saveState())
        self.closeInstrument()
        QMainWindow.closeEvent(self,event)

    #do these things when a sweep completes (or is canceled by the user)
    def doSweepComplete(self):
        if self.ui.sweepContinuallyGroup.isChecked() and self.sweeping: #in continual sweep mode, perform another sweep
            self.sendCmd(':source:' + self.source + ' {0:.4f}'.format(float(self.ui.startSpin.value())/1000))
            if self.ui.displayBlankCheck.isChecked():
                self.sendCmd(':display:enable off')#this makes the device more responsive
            else:
                self.sendCmd(':display:enable on')#this makes the device more responsive

            sleepMS = int(self.ui.scanRecoverySpin.value()*1000)
            if sleepMS > 0:
                #start these after the user specified delay
                self.timerA = QTimer()                
                self.timerA.timeout.connect(self.initiateNewSweep)
                self.timerA.setSingleShot(True)
                self.timerA.start(sleepMS)

                self.ui.statusbar.showMessage("Sleeping for {0:.1f} s before next scan".format(float(sleepMS)/1000),sleepMS)
            else: #no delay, don't use timers
                self.initiateNewSweep()

        else:#we're done sweeping
            self.sweeping = False
            self.ui.progress.setValue(0)

            #enable controls now that the sweep is complete
            self.ui.terminalsGroup.setEnabled(True)
            self.ui.wiresGroup.setEnabled(True)
            self.ui.modeGroup.setEnabled(True)
            self.ui.complianceGroup.setEnabled(True)
            self.ui.sweepGroup.setEnabled(True)
            self.ui.daqGroup.setEnabled(True)
            self.ui.outputCheck.setEnabled(True)
            self.ui.addressGroup.setEnabled(True)

            self.ui.sweepButton.setText('Start Sweep')
            
            self.ui.outputCheck.setChecked(self.userWantsOn)
            self.sendCmd(':source:' + self.source + ' {0:.4f}'.format(float(self.ui.startSpin.value())/1000))
            #self.sendCmd(":SYST:KEY 23")
        
    #update progress bar
    def updateProgress(self, value):
        self.ui.progress.setValue(value)

    #reverse sweep start and end points
    def reverseCall(self):
        startValue = self.ui.startSpin.value()
        endValue = self.ui.endSpin.value()

        #block signals momentarily while we swap things
        self.ui.endSpin.blockSignals(True)
        self.ui.startSpin.blockSignals(True)

        self.ui.endSpin.setValue(startValue)
        self.ui.startSpin.setValue(endValue)

        self.ui.endSpin.blockSignals(False)
        self.ui.startSpin.blockSignals(False)

        #update associated elements now that the swap is complete
        self.setStart()

    #turn output on or off when output box in gui changes state
    def setOutput(self):
        if self.ui.outputCheck.isChecked():
            self.sendCmd(":output on")
            #self.sendCmd(":SYST:KEY 23") #go into local mode for live display update
        else:
            self.sendCmd(":output off")
            
    def initiateNewSweep(self):
        if self.ui.saveModeCombo.currentIndex() == 0: #this is an I,V vs t sweep
            #start sweeping and measuring
            self.readRealTimeDataThread.start()
            self.measureThread.start()
            self.sweepThread.start()
        else: # this is an I vs V sweep
            self.sendCmd(':source:'+self.source+':mode sweep')
            self.ivDataThread.start()        

    #do these things when the user presses the sweep button
    def manageSweep(self):
        
        if self.ui.maxPowerCheck.isChecked():
            self.maxPowerDwell() #TODO this should go into the background
        else:
            if not self.sweeping:
    
                #disallow user from fucking shit up while the sweep is taking place
                self.ui.terminalsGroup.setEnabled(False)
                self.ui.wiresGroup.setEnabled(False)
                self.ui.modeGroup.setEnabled(False)
                self.ui.complianceGroup.setEnabled(False)
                self.ui.sweepGroup.setEnabled(False)
                self.ui.daqGroup.setEnabled(False)
                self.ui.outputCheck.setEnabled(False)
                self.ui.addressGroup.setEnabled(False)
    
                #calculate sweep parameters from data in gui elements
                self.ui.outputCheck.setChecked(True)
                nPoints = float(self.ui.totalPointsSpin.value())
                start = float(self.ui.startSpin.value())/1000
                end = float(self.ui.endSpin.value())/1000
                step = (end - start)/nPoints
                
                if start <= end:
                    self.sweepUp = True
                else:
                    self.sweepUp = False
    
                #sweep parameters
                dt = self.ui.delaySpinBox.value()
                sweepValues = np.linspace(start,end,nPoints)
    
                if self.ui.displayBlankCheck.isChecked():
                    self.sendCmd(':display:enable off')#this makes the device more responsive
    
                #send sweep parameters to the sweep thread
                self.sweepVaribles.emit(dt,sweepValues,self.source)
                self.sweeping = True
                
                self.initiateNewSweep()
                self.ui.sweepButton.setText('Abort Sweep')
    
            else:#sweep cancelled mid-run by user
                self.sweeping = False
                self.ui.statusbar.showMessage("Sweep aborted",self.messageDuration)
                self.ui.sweepButton.setEnabled(False)
                if hasattr(self,'timerA') and self.timerA.isActive():
                    self.timerA.stop()
                    self.timerB.stop()
                    self.timerC.stop()
                else:#sweep dealy tiemrs are not running, we're mid-sweep, send the kill signal
                    if self.ui.saveModeCombo.currentIndex() == 0:# we're in I,V vs t mode
                        self.sweepThread.terminate()
                        self.measureThread.timeToDie()
                    else: # we're in I vs V mode
                        self.k.clearInterface()
                        self.doSweepComplete()


    def saveOutputFile(self):
        #TODO: save sweep direction
        if self.ui.saveModeCombo.currentIndex() == 0:# we're in I,V vs t mode
            self.postProcessThread.saveTime = True 
        else:  # we're in I vs V mode
            self.postProcessThread.saveTime = False
        self.postProcessThread.area = str(self.ui.deviceAreaEdit.text())
        
        self.postProcessThread.savePath = os.path.join(str(self.ui.dirEdit.text()),str(self.ui.fileEdit.text()))
        
        self.postProcessThread.tempFile = QTemporaryFile()
        
        self.postProcessThread.sweepUp = self.sweepUp
        
        self.postProcessThread.start()
        
    def processingDone(self):
        self.ui.sweepButton.setEnabled(True)

    def initialSetup(self):
        try:
            #create the post processing thread and give it the keithley's done queue so that it can pull data from it
            self.postProcessThread = postProcessThread()
            
            self.ivDataThread = ivDataThread(self.k.task_queue,self.k.done_queue)
            self.ivDataThread.postData.connect(self.postProcessThread.acceptNewData)
            self.ivDataThread.postData.connect(self.doSweepComplete)                

            #create the measurement thread and give it the keithley's task queue so that it can issue commands to it
            self.measureThread = measureThread(self.k.task_queue)
            
            #create the data reading thread and give it the keithley's done queue so that it can grab data from it
            self.readRealTimeDataThread = readRealTimeDataThread(self.k.done_queue)

            #create the sweep thread and give it the keithley's task queue so that it can issue commands to it
            self.sweepThread = sweepThread(self.k.task_queue)

            #self.measureThread.measureDone.connect(self.collectDataThread.catchPointNumber)
            self.measureThread.measureDone.connect(self.readRealTimeDataThread.updatePoints)
            #self.collectDataThread.readyToCollect.connect(self.collectDataThread.start)

            #now connect  all the signals associated with these threads:
            #update the progress bar during the sweep
            self.sweepThread.updateProgress.connect(self.updateProgress)

            #update gui and shut off the output only when the last data point has been collected properly
            #self.collectAndSaveDataThread.dataCollectionDone.connect(self.doSweepComplete)

            #here the collected data is sent to the post processing thread
            self.readRealTimeDataThread.postData.connect(self.postProcessThread.acceptNewData)
            self.readRealTimeDataThread.postData.connect(self.doSweepComplete)
            
            #here the post process thread signals that it has the data and it's ready to start processing 
            self.postProcessThread.readyToProcess.connect(self.saveOutputFile)

            #tell the measurement to stop when the sweep is done
            self.sweepThread.sweepComplete.connect(self.measureThread.timeToDie)

            #give the new user entered sweep variables to the sweep thread
            self.sweepVaribles.connect(self.sweepThread.updateVariables)
            
            self.postProcessThread.postProcessingComplete.connect(self.processingDone)

            #kill sweep early on user request
            #self.killSweepNow.connect(self.sweepThread.earlyKill)
            #self.killSweepNow.connect(self.collectAndSaveDataThread.earlyKill)
            #TODO: should immediately stop threads and purge queue on user cancel

            self.sendCmd(":format:data sreal")
            self.sendCmd(':system:beeper:state 0') #make this quiet

            #always measure current and voltage
            self.sendCmd(':sense:function:concurrent on')

            self.setTerminals()
            self.setWires()
            self.sendCmd(":trace:feed:control never") #don't ever store data in buffer
            self.setZero()

            self.sendCmd(':sense:average:tcontrol repeat') #repeating averaging (not moving)
            self.setAverage()

            self.sendCmd(':format:elements time,voltage,current,status') #set data measurement elements
            self.sendCmd(':trigger:delay 0')
            
            self.sendCmd(':source:sweep:spacing linear')
            self.sendCmd(':source:sweep:ranging best')
            
            self.setMode() #sets output mode (current or voltage)
 
            self.setOutput()
            return True
        except:
            return False



    #do these things right after the user chooses on an instrument address
    def initialConnect(self,instrumentAddress):
        #this prevents the user from hammering this function through the GUI
        self.ui.sweepButton.setFocus()
        self.ui.sweepButton.setEnabled(False)

        try:
            #now that the user has selected an address for the keithley, let's connect to it. we'll use the thread safe version of the visa/gpib interface since we have multiple threads here
            self.k = gpib(instrumentAddress,useQueues=True,timeout=None)

            #self.k.task_queue.put(('clear',()))
            #self.sendCmd(':abort')
            self.sendCmd("*rst")
            #self.sendCmd('*cls')
            self.k.task_queue.put(('ask',('*idn?',)))
            try:
                ident = self.k.done_queue.get(block=True,timeout=10)
                self.ui.statusbar.showMessage("Connected to " + ident,self.messageDuration)
            except:
                ident = []

            #silly check here, if the instrument returned an identification string larger than 30 characters
            #assume it's okay to perform a sweep
            modelString = "MODEL 2400"
            firmwareString = "C32"
            if ident.__contains__(modelString):
                if ident.__contains__(firmwareString):
                    self.k.task_queue.put(('ask',(':system:mep:state?',)))
                    isSCPI = self.k.done_queue.get()
                    if isSCPI == '0':
                        if self.initialSetup():
                            self.ui.sweepButton.setEnabled(True)
                            self.ui.sweepButton.setFocus()
                            self.ui.sweepButton.setDefault(True)
                        else:
                            self.closeInstrument()
                            self.ui.statusbar.showMessage("Setup failed")                      
                    else:
                        self.closeInstrument()
                        self.ui.statusbar.showMessage("SCPI comms mode detected")                        
                        msgBox = QMessageBox()
                        msgBox.setWindowTitle("SCPI mode detected. Please sqitch to 488.1 mode.")
                        message488 = \
                            "Perform the following steps to select the 488.1 protocol:\n" + \
                            "1. Press MENU to display the MAIN MENU.\n" + \
                            "2. Place the cursor on COMMUNICATION and press ENTER to display the COMMUNICATIONS SETUP menu.\n" + \
                            "3. Place the cursor on GPIB and press ENTER to display the present GPIB address.\n" + \
                            "4. Press ENTER to display the GPIB PROTOCOL menu.\n" + \
                            "5. Place the cursor on 488.1 and press ENTER.\n" + \
                            "6. Use the EXIT key to back out of the menu structure."
                        msgBox.setText(message488);
                        msgBox.exec_();
                else:
                    self.closeInstrument()
                    self.ui.statusbar.showMessage('{0:s} found, firmware {1:s} not detected. Please upgrade firmware to continue.'.format(modelString,firmwareString))                    
            else:
                self.closeInstrument()
                self.ui.statusbar.showMessage('Could not detect instrument with "{0:s}"'.format(modelString))

        except:
            self.closeInstrument()
            self.ui.statusbar.showMessage("Connection failed")


    #tell keithely to change compliance when on gui compliance change events
    def setCompliance(self):
        self.ui.outputCheck.setChecked(False)
        value = float(self.ui.complianceSpin.value())
        self.sendCmd(':sense:'+self.sense+':protection {0:.3f}'.format(value/1000))
        self.sendCmd(':sense:'+self.sense+':range {0:.3f}'.format(value/1000))
        self.ui.outputCheck.setChecked(self.userWantsOn)

    #tell keithely to change nplc and digits displayed when on gui speed change events
    def setSpeed(self):
        value = self.ui.speedCombo.currentIndex()
        if value is 0: #fast
            self.sendCmd(':sense:'+self.sense+':nplcycles 0.01')
            self.sendCmd(':display:digits 4')
        elif value is 1: #med
            self.sendCmd(':sense:'+self.sense+':nplcycles 0.1')
            self.sendCmd(':display:digits 5')
        elif value is 2: #normal
            self.sendCmd(':sense:'+self.sense+':nplcycles 1')
            self.sendCmd(':display:digits 6')
        elif value is 3: #hi accuracy
            self.sendCmd(':sense:'+self.sense+':nplcycles 10')
            self.sendCmd(':display:digits 7')

    #tell keithely to change the internal averaging it does on gui average change events
    def setAverage(self):
        value = self.ui.averageSpin.value()
        if value is 0: #no averaging
            self.sendCmd(':sense:average off')
        else:
            self.sendCmd(':sense:average on')
            self.sendCmd(':sense:average:count {0}'.format(value))

    #tell keithley to enable/disable auto zero when the gui auto zero check box changes state
    def setZero(self):
        if self.ui.zeroCheck.isChecked():
            self.sendCmd(":system:azero on")
        else:
            self.sendCmd(":system:azero off")

    #do all the things needed when the source sweep range is changed
    def setSourceRange(self):
        startValue = float(self.ui.startSpin.value())
        endValue = float(self.ui.endSpin.value())        
        if self.ui.saveModeCombo.currentIndex() == 0: #only set max here if we're in i,v vs t mode
            span = abs(endValue-startValue)+1
            self.ui.totalPointsSpin.setMaximum(span)
            

        self.updateDeltaText()

        maxAbs = max(abs(startValue),abs(endValue))
        self.sendCmd(':source:'+self.source+':range {0:.3f}'.format(maxAbs/1000))


    #do what needs to be done when the sweep start value is modified
    def setStart(self):
        startValue = float(self.ui.startSpin.value())
        self.setSourceRange()
        self.sendCmd('source:'+self.source+' {0:.3f}'.format(startValue/1000))


    #do these things when the user changes the sweep mode (from voltage to current or the reverse)
    def setMode(self):
        self.ui.outputCheck.setChecked(False) #output gets shut off during source change

        if self.ui.sourceVRadio.isChecked(): #sweep in voltage
            self.source = "voltage"
        else:#sweep in current
            self.source = "current"
        self.ui.outputCheck.setChecked(self.userWantsOn)

        self.sendCmd(":source:function " + self.source)

        if self.ui.sourceVRadio.isChecked(): #sweep in voltage
            self.sense = "current"
            self.sourceUnit = 'V'
            self.complianceUnit = 'A'
            self.ui.startSpin.setRange(-20000,20000)
            self.ui.endSpin.setRange(-20000,20000)
            self.ui.complianceSpin.setRange(1,1000)
            self.sendCmd(':sense:function "current:dc", "voltage:dc"')
            self.sendCmd(":source:"+self.source+":mode fixed") #fixed output mode
        else: #sweep in current
            self.sense = "voltage"
            self.sourceUnit = 'A'
            self.complianceUnit = 'V'
            self.ui.startSpin.setRange(-1000,1000)
            self.ui.endSpin.setRange(-1000,1000)
            self.ui.complianceSpin.setRange(1,20000)
            self.sendCmd(':sense:function  "voltage:dc","current:dc"')
            self.sendCmd(":source:"+self.source+":mode fixed") #fixed output mode
        self.ui.startSpin.setSuffix(' m{0:}'.format(self.sourceUnit))
        self.ui.endSpin.setSuffix(' m{0:}'.format(self.sourceUnit))
        self.ui.complianceSpin.setSuffix(' m{0:}'.format(self.complianceUnit))
        self.setStart()
        self.setCompliance()
        self.setSpeed()
        self.handleModeCombo() #sets i vs v or i,v vs t mode

    #do these things just before program termination to ensure the computer and instrument are left in a friendly state
    def closeInstrument(self):
        try:
            self.sweeping = False
            self.measureThread.timeToDie()
        except:
            pass
            
        try:
            #self.killSweepNow.emit()
            self.sweepThread.terminate()
        except:
            pass
        
        try:
            self.k.task_queue.put(('clear',()))
        except:
            pass
        #TODO: reenable this
        #gpib().clearInterface()
        self.sendCmd(':abort')
        self.sendCmd(':arm:count 1')
        self.sendCmd(":display:enable on")
        self.sendCmd(":display:window1:text:state off")
        self.sendCmd(":display:window2:text:state off")
        self.sendCmd('*rst')
        self.sendCmd('*cls')
        self.sendCmd(':system:key 23')
        
        try:
            self.k.__del__() #cleanup
            del self.k #remove
        except:
            pass


    def setTerminals(self):
        self.ui.outputCheck.setChecked(False)
        if self.ui.frontRadio.isChecked():
            self.sendCmd(":route:terminals front")
        else:
            self.sendCmd(":route:terminals rear")
        self.ui.outputCheck.setChecked(self.userWantsOn)

    def updateDeltaText(self):
        #tTot = float(self.ui.totalTimeSpin.value())
        dt = self.ui.delaySpinBox.value()
        nPoints = float(self.ui.totalPointsSpin.value())
        start = float(self.ui.startSpin.value())
        end = float(self.ui.endSpin.value())
        span = end-start
        tTot = dt*nPoints
        
        if self.ui.saveModeCombo.currentIndex() == 1:# we're in i vs v mode
            self.sendCmd(':trigger:count {0:d}'.format(int(nPoints)))
            self.sendCmd(":source:delay {0:0.3f}".format(dt))
            self.sendCmd(':source:sweep:points {0:d}'.format(int(nPoints)))
        
        self.sendCmd(':source:'+self.source+':start {0:.3f}'.format(start/1000))
        self.sendCmd(':source:'+self.source+':stop {0:.3f}'.format(end/1000))
        #self.sendCmd(':source:'+self.source+':step {0:.3f}'.format(step))
        
        if tTot >= 60:
            timeText = QString(u'tot={0:.1f} min'.format(tTot/60))
        else:
            timeText = QString(u'tot={0:.3f} s'.format(tTot))
        self.ui.totalLabel.setText(timeText)

        if nPoints == 1:            
            stepText = QString(u'Δ=NaN m{0:}'.format(self.sourceUnit))
        else:
            stepText = QString(u'Δ={0:.0f} m{1:}'.format(span/(nPoints-1),self.sourceUnit))
        self.ui.deltaStep.setText(stepText)

    def setWires(self):
        self.ui.outputCheck.setChecked(False)
        if self.ui.twowireRadio.isChecked():
            self.sendCmd(":system:rsense OFF")
        else:
            self.sendCmd(":system:rsense ON")
        self.ui.outputCheck.setChecked(self.userWantsOn)
        
    def sendCmd(self,cmdString):
        try:
            self.k.write(cmdString)
            #self.k.write(":system:key 23") #go into local mode for live display update AFTER EVERY COMMAND!
        except:
            self.ui.statusbar.showMessage("Command failed",self.messageDuration);

if __name__ == "__main__":
    app = QApplication(sys.argv)
    sweeper = MainWindow()
    sweeper.show()
    sys.exit(app.exec_())
