# -*- coding: utf-8 -*-
"""
This is a program to control a keithley 2400 sourcemeter.
It allows for high frequency (~150Hz at present) sampling during I-V sourcemeasurements to gain insight into some device dynamics
@author: grey
"""
import os, sys, inspect
#these lines ensure the proper folders are in the python path no matter how this script gets run
cmd_folder = os.path.realpath(os.path.abspath(os.path.split(inspect.getfile( inspect.currentframe() ))[0]))
if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)

#here we include one folder up(where the folder pygrey should live)
cmd_subfolder = os.path.realpath(os.path.abspath(os.path.join(os.path.split(inspect.getfile( inspect.currentframe() ))[0],"..")))
if cmd_subfolder not in sys.path:
    sys.path.insert(0, cmd_subfolder)

try:
    from gpib import gpib
    gotGPIB = True
except:
    gotGPIB = False
    print "Could not import GPIB"

import math
from PyQt4.QtCore import QString, QThread, pyqtSignal, QTimer, QSettings
from PyQt4.QtGui import QApplication, QDialog, QMainWindow, QFileDialog, QMessageBox
from selectInstrumentUI import Ui_instrumentSelection
from ivSweeperUI import Ui_IVSweeper
from resultsUI import Ui_results
from scipy.special import lambertw
from scipy.optimize import curve_fit
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
    sweepComplete = pyqtSignal(bool) #indicates sweep is complete, carries True if it was a premature termination

    def __init__(self, q, parent=None):
        QThread.__init__(self, parent)

        self.q = q #gpib command queue

        self.prematureTermination = False

    def updateVariables(self,dt,sweepPoints,sourceName):
        self.dt = dt
        self.sweepPoints = sweepPoints
        self.sourceName = sourceName

    def earlyKill(self):
        self.prematureTermination = True

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
            if self.prematureTermination: #sweep termination only has time resolution of dt, oh well
                break
        self.sweepComplete.emit(self.prematureTermination)
        self.prematureTermination = False

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
        self.measureDone.emit(dataPoints)

#here is the characteristic equation for solar cells, solved for I
#we'll use it to extract the modelling parameters we're interested in
#need to use lambert w function here in order to be able to solve for I explicitly
#this method is from http://dx.doi.org/10.1016/j.solmat.2003.11.018
def charEqn(V,I0,Iph,n,Rs,Rsh):
    Vth = 0.0259#thermal voltage at 25c
    #todo: check on the real here
    return np.real(Rsh*(I0+Iph)/(Rs+Rsh)-V/(Rs+Rsh)-lambertw((Rs*I0*Rsh)/(n*Vth*(Rs+Rsh))*np.exp((Rsh*(Rs*Iph+Rs*I0+V))/(n*Vth*(Rs+Rsh))))*n*Vth/Rs)

class postProcessThread(QThread):
    readyToProcess = pyqtSignal() #signal when we're ready to post process
    postProcessingDone = pyqtSignal(dict,np.ndarray)
    def __init__(self, parent=None):
        QThread.__init__(self, parent)

    def acceptNewData(self,data):
        self.rawData = data
        self.readyToProcess.emit()

    def run(self):
        Vth = 0.0259#thermal voltage at 25c
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

        parameters = {'00_nSamples': len(t), \
                      '01_pMaxRaw[mW]': pmaxRaw*1000, \
                      '02_worstSpeed[Hz]': 1/maxdt, \
                      '03_worstSpeed[ms]':  maxdt*1000, \
                      '04_bestSpeed[Hz]': 1/mindt, \
                      '05_bestSpeed[ms]':  mindt*1000, \
                      '06_meanSpeed[Hz]': 1/meandt, \
                      '07_meanSpeed[ms]':  meandt*1000}
        try:
            popt, pcov = curve_fit(charEqn, v, i)
            I0 = popt[0]
            Iph = popt[1]
            n = popt[2]
            Rs = popt[3]
            Rsh = popt[4]
            Voc = n*Vth*math.log(Iph/I0+1)
            Isc = Iph
            #double check this:
            #optimal voltage:
            Vmax = Voc - Vth*math.log(1+Voc/Vth)
            Imax = -Iph*(1-Vth/Vmax)
            Pmax = Vmax*Imax
            ff = (Pmax)/Voc*Isc
            parameters['08_Rs[ohm]'] = Rs
            parameters['09_Rsh[ohm]'] = Rsh
            parameters['10_n'] = n
            parameters['11_I0'] = I0
            parameters['12_Isc'] = Isc
            parameters['13_Voc'] = Voc
            parameters['14_Vmax'] = Vmax
            parameters['15_Imax'] = Imax
            parameters['16_Pmax'] = Pmax
            parameters['17_ff'] = ff
        except:
            parameters['08_note'] = 'could not fit data to solar cell model'
        self.postProcessingDone.emit(parameters,self.rawData)

#here we have the thread that picks the data out of the visa done queue readies it for public consumption, and sends it to the post processor
class collectDataThread(QThread):
    dataCollectionDone = pyqtSignal() #signal when we've collected the final data point
    readyToCollect = pyqtSignal() #signal when we're ready to collect data
    postData = pyqtSignal(np.ndarray) #send away the data collected here
    def __init__(self, q, parent=None):
        QThread.__init__(self, parent)

        self.q = q #gpib done queue
        self.prematureTermination = False

    def earlyKill(self):
        self.prematureTermination = True

    def catchPointNumber(self,needToCollect):
        self.needToCollect = needToCollect
        self.readyToCollect.emit()

    def run(self):
        data = [None]*self.needToCollect
        
        for i in range(self.needToCollect): 
            data[i] = qBinRead(q)

        #signal that we're done
        self.dataCollectionDone.emit()

        if (len(data) >2) and not self.prematureTermination:
            #convert to array:
            data = np.array(data)

            #sort it by time(the 3rd col), because who knows what order we got it
            data = data[data[:,2].argsort()]

            self.postData.emit(data)
        self.prematureTermination = False



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

class ResultsDialog(QDialog):
    def __init__(self):
        QDialog.__init__(self)

        # Set up the user interface from Designer.
        self.ui = Ui_results()
        self.ui.setupUi(self)
        self.rawData = []

        self.ui.saveButton.clicked.connect(self.saveCall)

    def saveCall(self):
        fileName = QFileDialog.getSaveFileName()
        np.savetxt(str(fileName), self.rawData)

    def catchUpdate(self,postProcessData,rawData):
        self.postProcessData = postProcessData
        self.rawData = rawData
        self.updateResults()

    def updateResults(self):
        output = ''
        od = OrderedDict(sorted(self.postProcessData.items()))
        for a,b in od.items():
            output = output+ str(a)+': '+str(b)+ '\n'
        self.ui.summaryArea.setText(output)
        if not self.isVisible():
            self.show()


#this is the dialog that the user uses to choose which instrument they wish to communicate with
class SelectDialog(QDialog):
    def __init__(self):
        QDialog.__init__(self)

        # Set up the user interface from Designer.
        self.ui = Ui_instrumentSelection()
        self.ui.setupUi(self)

        self.ui.refreshButton.clicked.connect(self.populateList)
        self.ui.okButton.clicked.connect(self.saveSelection)

        self.instrumentDetectThread = instrumentDetectThread()

        self.instrumentDetectThread.foundInstruments.connect(self.catchList)
        self.ui.okButton.setEnabled(False)

#gets the list from instrument detection thread
    def catchList(self,resourceNames):
        self.ui.instrumentList.clear()
        self.ui.instrumentList.addItems(resourceNames)
        self.ui.instrumentList.item(0).setSelected(True)
        self.ui.okButton.setEnabled(True)

#populate the list once the window is drawn
    def showEvent(self, event):
        self.populateList()

#call the instrument search thread
    def populateList (self):
        self.ui.okButton.setEnabled(False)
        self.ui.instrumentList.clear()
        self.ui.instrumentList.addItems(["Searching for instruments..."])
        self.instrumentDetectThread.start()

#send the user's selection to the main window
    def saveSelection (self):
        selectedInstrument = self.ui.instrumentList.selectedItems()[0].text()
        if selectedInstrument == "None found":
            return
        
        self.mainWindow.ui.addressField.setText(selectedInstrument)
        self.mainWindow.initialConnect()

#this is the main gui window
class MainWindow(QMainWindow):
    sweepVaribles = pyqtSignal(float,np.ndarray,str)
    killSweepNow = pyqtSignal()
    def __init__(self,finder,results):
        QMainWindow.__init__(self)

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

        #keep track of if we have created the results window or not
        self.resultsWindowExists = False

        # Set up the user interface from Designer.
        self.ui = Ui_IVSweeper()
        self.ui.setupUi(self)

        #store away instrument search dialog object
        self.finder = finder
        self.results = results

        self.ui.addressField.setStyleSheet("QLineEdit { background-color : yellow;}")

        #connect signals generated by gui elements to proper functions        
        self.ui.findButton.clicked.connect(self.launchFinder)
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
        self.ui.totalTimeSpin.valueChanged.connect(self.totalTimeCall)
        self.ui.totalPointsSpin.valueChanged.connect(self.totalPointsCall)
        self.ui.reverseButton.clicked.connect(self.reverseCall)
        self.ui.actionRun_Test_Code.triggered.connect(self.testArea)
        #self.ui.plotButton.clicked.connect(self.plotCall)
        #self.ui.addressField.editingFinished.connect(self.initialConnect) #this doesn't work, incorrect addresses here crash things

        #TODO: load state here
        #self.restoreState(self.settings.value('guiState').toByteArray())
        
    
        
    
    #return -1 * the power of the device at a given voltage or current
    def invPower(self,independantVariable):
        
        try:
            self.k.write(':source:'+self.source+':range {0:.5f}'.format(independantVariable))
            self.q.put(('read_raw',()))
            data = qBinRead(self.k.done_queue)
            return (data[0]*data[1]*-1)
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration);
            return np.nan
        
        
    def handleShutter(self):
        shutterOnValue = '14'
        shutterOffValue = '15'
        try:
            self.k.task_queue.put(('ask',(':source2:ttl:actual?',)))
            outStatus = self.k.done_queue.get()
            if outStatus == shutterOnValue:
                self.k.write(":source2:ttl " + shutterOffValue)
            else:
                self.k.write(":source2:ttl " + shutterOnValue)
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration)

    def testArea(self):
        print('Running test code now')
        

        
        #self.ui.statusbar.showMessage("Connection aborted switch to",self.messageDuration)
        
        #t = time.time()
        #powerTime = 15#seconds
        #vMaxGuess = 0.7
        #while toc < powerTime:
            #optimize.minimize(self.InvPower,vMaxGuess)
            #self.q.put(('read_raw',()))
            #data = qBinRead(self.k.done_queue)        
            #vi = (data[0], data[1], data[1]*data[0]*1000)
            #print vi
            #toc = time.time() - t
        
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
            self.k.write(':source:' + self.source + ' {0:.4f}'.format(float(self.ui.startSpin.value())/1000))
            if self.ui.displayBlankCheck.isChecked():
                self.k.write(':display:enable off')#this makes the device more responsive
            else:
                self.k.write(':display:enable on')#this makes the device more responsive

            sleepMS = int(self.ui.scanRecoverySpin.value()*1000)
            if sleepMS > 0:
                #start these after the user specified delay
                self.timerA = QTimer()
                self.timerB = QTimer()
                self.timerA.timeout.connect(self.measureThread.start)
                self.timerA.setSingleShot(True)
                self.timerB.timeout.connect(self.sweepThread.start)
                self.timerB.setSingleShot(True)
                self.timerA.start(sleepMS)
                self.timerB.start(sleepMS)

                self.ui.statusbar.showMessage("Sleeping for {0:.1f} s before next scan".format(float(sleepMS)/1000),sleepMS)
            else: #no delay, don't use timers
                self.measureThread.start()
                self.sweepThread.start()

        else:#we're done sweeping
            self.sweeping = False

            #enable controls now that the sweep is complete
            self.ui.terminalsGroup.setEnabled(True)
            self.ui.wiresGroup.setEnabled(True)
            self.ui.modeGroup.setEnabled(True)
            self.ui.complianceGroup.setEnabled(True)
            self.ui.findButton.setEnabled(True)
            self.ui.sweepGroup.setEnabled(True)
            self.ui.daqGroup.setEnabled(True)
            self.ui.outputCheck.setEnabled(True)
            self.ui.addressGroup.setEnabled(True)

            self.ui.sweepButton.setText('Start Sweep')
            self.ui.outputCheck.setChecked(False)
            self.k.write(':source:' + self.source + ' {0:.4f}'.format(float(self.ui.startSpin.value())/1000))
            self.k.write(':display:enable on')#this makes the device more responsive

    #update progress bar
    def updateProgress(self, value):
        self.ui.progress.setValue(value)

    #launch instrument finder window
    def launchFinder(self):
        self.finder.mainWindow = self
        self.finder.show()

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
        try:
            if self.ui.outputCheck.isChecked():
                self.k.write(":output on")
            else:
                self.k.write(":output off")
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration)

    #do these things when the user presses the sweep button
    def manageSweep(self):
        if not self.sweeping:

            #disallow user from fucking shit up while the sweep is taking place
            self.ui.terminalsGroup.setEnabled(False)
            self.ui.wiresGroup.setEnabled(False)
            self.ui.modeGroup.setEnabled(False)
            self.ui.complianceGroup.setEnabled(False)
            self.ui.findButton.setEnabled(False)
            self.ui.sweepGroup.setEnabled(False)
            self.ui.daqGroup.setEnabled(False)
            self.ui.outputCheck.setEnabled(False)
            self.ui.addressGroup.setEnabled(False)

            #calculate sweep parameters from data in gui elements
            self.ui.outputCheck.setChecked(True)
            tTot = float(self.ui.totalTimeSpin.value())
            nPoints = float(self.ui.totalPointsSpin.value())
            start = float(self.ui.startSpin.value())/1000
            end = float(self.ui.endSpin.value())/1000

            #sweep parameters
            dt = tTot/nPoints
            sweepValues = np.linspace(start,end,nPoints)

            if self.ui.displayBlankCheck.isChecked():
                self.k.write(':display:enable off')#this makes the device more responsive

            #send sweep parameters to the sweep thread
            self.sweepVaribles.emit(dt,sweepValues,self.source)
            self.sweeping = True

            #start sweeping and measuring
            self.measureThread.start()
            self.sweepThread.start()

            self.ui.sweepButton.setText('Abort Sweep')

        else:#sweep cancelled mid-run by user
            self.sweeping = False
            self.ui.statusbar.showMessage("Sweep aborted",self.messageDuration)
            if hasattr(self,'timerA') and self.timerA.isActive():
                self.timerA.stop()
                self.timerB.stop()
                self.doSweepComplete()
            else:#sweep dealy tiemrs are not running, we're mid-sweep, send the kill signal
                self.killSweepNow.emit()


    #do these things right after the user chooses on an instrument address
    def initialConnect(self):
        self.ui.addressField.setStyleSheet("QLineEdit { background-color : yellow;}")
        #this prevents the user from hammering this function through the GUI
        self.ui.sweepButton.setFocus()
        self.ui.sweepButton.setEnabled(False)
        
        instrumentAddress = str(self.ui.addressField.text())

        try:
            #now that the user has selected an address for the keithley, let's connect to it. we'll use the thread safe version of the visa/gpib interface since we have multiple threads here
            self.k = gpib(instrumentAddress,useQueues=True)
            
            self.k.task_queue.put(('ask',(':system:mep:state?',)))
            isSCPI = self.k.done_queue.get()
            print isSCPI
            #msgBox = QMessageBox()
            #msgBox.setText("The document has been modified.");
            #msgBox.exec_();
    
            self.collectDataThread  = collectDataThread(self.k.done_queue)

            #create the post processing thread and give it the keithley's done queue so that it can pull data from it
            self.postProcessThread = postProcessThread()

            #create the measurement thread and give it the keithley's task queue so that it can issue commands to it
            self.measureThread = measureThread(self.k.task_queue)

            #create the sweep thread and give it the keithley's task queue so that it can issue commands to it
            self.sweepThread = sweepThread(self.k.task_queue)

            self.measureThread.measureDone.connect(self.collectDataThread.catchPointNumber)
            self.collectDataThread.readyToCollect.connect(self.collectDataThread.start)

            #now connect  all the signals associated with these threads:
            #update the progress bar during the sweep
            self.sweepThread.updateProgress.connect(self.updateProgress)

            #update gui and shut off the output only when the last data point has been collected properly
            self.collectDataThread.dataCollectionDone.connect(self.doSweepComplete)

            self.collectDataThread.postData.connect(self.postProcessThread.acceptNewData)

            self.postProcessThread.readyToProcess.connect(self.postProcessThread.start)

            #self.postProcessThread.postProcessingDone.connect(self.postResults)
            self.postProcessThread.postProcessingDone.connect(self.results.catchUpdate)

            #tell the measurement to stop when the sweep is done
            self.sweepThread.sweepComplete.connect(self.measureThread.timeToDie)

            #give the new user entered sweep variables to the sweep thread
            self.sweepVaribles.connect(self.sweepThread.updateVariables)

            #kill sweep early on user request
            self.killSweepNow.connect(self.sweepThread.earlyKill)
            self.killSweepNow.connect(self.collectDataThread.earlyKill)

            self.k.task_queue.put(('clear',()))
            self.k.write(':abort')
            self.k.write("*rst")
            self.k.write('*cls')
            self.k.task_queue.put(('ask',('*idn?',)))
            ident = self.k.done_queue.get()            

            self.ui.statusbar.showMessage("Connected to " + ident,self.messageDuration)

            self.k.write(":format:data sreal")
            self.k.write(':system:beeper:state 0')

            #always measure current and voltage
            self.k.write(':sense:function:concurrent on')

            self.setMode() #sets output mode (current or voltage)

            self.setTerminals()
            self.setWires()
            self.k.write(":trace:feed:control never") #don't ever store data in buffer
            self.setZero()

            self.k.write(':sense:average:tcontrol repeat') #repeating averaging (not moving)
            self.setAverage()

            self.k.write(':format:elements time,voltage,current,status') #set data measurement elements
            self.k.write(":source:delay 0")
            self.k.write(':trigger:delay 0') 

            self.setOutput()

            #silly check here, if the instrument returned an identification string larger than 30 characters
            #assume it's okay to perform a sweep
            if len(ident) > 30:
                self.ui.sweepButton.setEnabled(True)
                self.ui.findButton.setDefault(False)
                self.ui.sweepButton.setFocus()
                self.ui.sweepButton.setDefault(True)
                self.ui.addressField.setStyleSheet("QLineEdit { background-color : green;}")
            else:
                self.ui.addressField.setStyleSheet("QLineEdit { background-color : red;}")
                self.ui.statusbar.showMessage("Connection failed")

        except:
            self.ui.addressField.setStyleSheet("QLineEdit { background-color : red;}")
            self.ui.statusbar.showMessage("Connection failed")


    #tell keithely to change compliance when on gui compliance change events
    def setCompliance(self):
        self.ui.outputCheck.setChecked(False)
        value = float(self.ui.complianceSpin.value())
        try:
            self.k.write(':sense:'+self.sense+':protection {0:.3f}'.format(value/1000))
            self.k.write(':sense:'+self.sense+':range {0:.3f}'.format(value/1000))
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration);

    #tell keithely to change nplc and digits displayed when on gui speed change events
    def setSpeed(self):
        value = self.ui.speedCombo.currentIndex()
        try:
            if value is 0: #fast
                self.k.write(':sense:'+self.sense+':nplcycles 0.01')
                self.k.write(':display:digits 4')
            elif value is 1: #med
                self.k.write(':sense:'+self.sense+':nplcycles 0.1')
                self.k.write(':display:digits 5')
            elif value is 2: #normal
                self.k.write(':sense:'+self.sense+':nplcycles 1')
                self.k.write(':display:digits 6')
            elif value is 3: #hi accuracy
                self.k.write(':sense:'+self.sense+':nplcycles 10')
                self.k.write(':display:digits 7')
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration);    

    #tell keithely to change the internal averaging it does on gui average change events
    def setAverage(self):
        value = self.ui.averageSpin.value()
        try:
            if value is 0: #no averaging
                self.k.write(':sense:average off')
            else:
                self.k.write(':sense:average on')
                self.k.write(':sense:average:count {0}'.format(value))
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration); 

    #tell keithley to enable/disable auto zero when the gui auto zero check box changes state
    def setZero(self):
        try:
            if self.ui.zeroCheck.isChecked():
                self.k.write(":system:azero on")
            else:
                self.k.write(":system:azero off")
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration);

    #do all the things needed when the source sweep range is changed
    def setSourceRange(self):
        startValue = float(self.ui.startSpin.value())
        endValue = float(self.ui.endSpin.value())
        span = abs(endValue-startValue)+1

        self.ui.totalPointsSpin.setMaximum(span)

        self.updateDeltaText()

        maxAbs = max(abs(startValue),abs(endValue))
        try:
            self.k.write(':source:'+self.source+':range {0:.3f}'.format(maxAbs/1000))

        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration);


    #do what needs to be done when the sweep start value is modified
    def setStart(self):
        startValue = float(self.ui.startSpin.value())
        self.setSourceRange()
        try:
            self.k.write('source:'+self.source+' {0:.3f}'.format(startValue/1000))
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration);

    #do these things when the user changes the sweep mode (from voltage to current or the reverse)
    def setMode(self):
        self.ui.outputCheck.setChecked(False) #output gets shut off during source change

        if self.ui.sourceVRadio.isChecked(): #sweep in voltage
            self.source = "voltage"
        else:#sweep in current
            self.source = "current"

        try:
            self.k.write(":source:function " + self.source)

        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration)

        if self.ui.sourceVRadio.isChecked(): #sweep in voltage
            self.sense = "current"
            self.sourceUnit = 'V'
            self.complianceUnit = 'A'
            self.ui.startSpin.setRange(-20000,20000)
            self.ui.endSpin.setRange(-20000,20000)
            self.ui.complianceSpin.setRange(1,1000)
            try:
                self.k.write(':sense:function "current:dc", "voltage:dc"')
                self.k.write(":source:"+self.source+":mode fixed") #fixed output mode
            except:
                self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration)
        else: #sweep in current
            self.sense = "voltage"
            self.sourceUnit = 'A'
            self.complianceUnit = 'V'
            self.ui.startSpin.setRange(-1000,1000)
            self.ui.endSpin.setRange(-1000,1000)
            self.ui.complianceSpin.setRange(1,20000)
            try:
                self.k.write(':sense:function  "voltage:dc","current:dc"')
                self.k.write(":source:"+self.source+":mode fixed") #fixed output mode
            except:
                self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration)
        self.ui.startSpin.setSuffix(' m{0:}'.format(self.sourceUnit))
        self.ui.endSpin.setSuffix(' m{0:}'.format(self.sourceUnit))
        self.ui.complianceSpin.setSuffix(' m{0:}'.format(self.complianceUnit))
        self.setStart()
        self.setCompliance()
        self.setSpeed()

    #do these things just before program termination to ensure the computer and instrument are left in a friendly state
    def closeInstrument(self):
        try:
            self.measureThread.timeToDie()
            self.sweeping = False
            self.killSweepNow.emit()
            self.doSweepComplete()
            self.k.task_queue.put(('clear',()))
            self.k.write(':abort')
            self.k.write(':arm:count 1')
            self.k.write(":display:enable on")
            self.k.write(":display:window1:text:state off")
            self.k.write(":display:window2:text:state off")
            self.k.write('*rst')
            self.k.write('*cls')
            self.k.write(':system:key 23')
            self.k.task_queue.put('STOP')#this terminates gpib driver queue worker properly
        except:
            print 'Instrument not properly disconnected'

    def setTerminals(self):
        self.ui.outputCheck.setChecked(False)
        try:
            if self.ui.frontRadio.isChecked():
                self.k.write(":route:terminals front")
            else:
                self.k.write(":route:terminals rear")
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration)

    def updateDeltaText(self):
        tTot = float(self.ui.totalTimeSpin.value())
        nPoints = float(self.ui.totalPointsSpin.value())
        start = float(self.ui.startSpin.value())
        end = float(self.ui.endSpin.value())
        span = end-start
        dt = tTot/nPoints

        timeText = QString(u'Δ={0:.0f} ms'.format(dt*1000))

        if nPoints == 1:            
            stepText = QString(u'Δ=NaN m{0:}'.format(self.sourceUnit))
        else:
            stepText = QString(u'Δ={0:.0f} m{1:}'.format(span/(nPoints-1),self.sourceUnit))
        self.ui.deltaStep.setText(stepText)
        self.ui.deltaTime.setText(timeText)

    def totalPointsCall(self,newValue):        
        #ensure that total time is not too short as total number of data points goes up
        tTotMin = float(newValue)*0.02
        if tTotMin < 2:
            tTotMin = 2
        tTotMin = math.ceil(tTotMin)
        self.ui.totalTimeSpin.setMinimum(tTotMin)


        self.updateDeltaText()

    def totalTimeCall(self,newValue):        
        self.updateDeltaText()   

    def setWires(self):
        self.ui.outputCheck.setChecked(False)
        try:
            if self.ui.twowireRadio.isChecked():
                self.k.write(":system:rsense OFF")
            else:
                self.k.write(":system:rsense ON")
        except:
            self.ui.statusbar.showMessage("Error: Not connected",self.messageDuration);
        self.setOutput()  

if __name__ == "__main__":
    app = QApplication(sys.argv)
    finder = SelectDialog()
    results = ResultsDialog()
    sweeper = MainWindow(finder,results)
    sweeper.show()
    #app.aboutToQuit.connect(sweeper.closeInstrument)
    sys.exit(app.exec_())
