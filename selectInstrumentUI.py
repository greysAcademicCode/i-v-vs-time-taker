# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'selectInstrument.ui'
#
# Created: Tue Jan 21 11:06:25 2014
#      by: PyQt4 UI code generator 4.9.6
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

try:
    _encoding = QtGui.QApplication.UnicodeUTF8
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig, _encoding)
except AttributeError:
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig)

class Ui_instrumentSelection(object):
    def setupUi(self, instrumentSelection):
        instrumentSelection.setObjectName(_fromUtf8("instrumentSelection"))
        instrumentSelection.resize(390, 287)
        self.refreshButton = QtGui.QPushButton(instrumentSelection)
        self.refreshButton.setGeometry(QtCore.QRect(10, 250, 75, 23))
        self.refreshButton.setAutoDefault(False)
        self.refreshButton.setObjectName(_fromUtf8("refreshButton"))
        self.instrumentList = QtGui.QListWidget(instrumentSelection)
        self.instrumentList.setGeometry(QtCore.QRect(9, 29, 371, 211))
        self.instrumentList.setObjectName(_fromUtf8("instrumentList"))
        item = QtGui.QListWidgetItem()
        self.instrumentList.addItem(item)
        self.okButton = QtGui.QPushButton(instrumentSelection)
        self.okButton.setGeometry(QtCore.QRect(300, 250, 75, 23))
        self.okButton.setAutoDefault(False)
        self.okButton.setDefault(True)
        self.okButton.setObjectName(_fromUtf8("okButton"))
        self.label = QtGui.QLabel(instrumentSelection)
        self.label.setGeometry(QtCore.QRect(10, 10, 361, 16))
        self.label.setObjectName(_fromUtf8("label"))

        self.retranslateUi(instrumentSelection)
        QtCore.QObject.connect(self.okButton, QtCore.SIGNAL(_fromUtf8("clicked()")), instrumentSelection.close)
        QtCore.QMetaObject.connectSlotsByName(instrumentSelection)

    def retranslateUi(self, instrumentSelection):
        instrumentSelection.setWindowTitle(_translate("instrumentSelection", "Instrument Selection", None))
        self.refreshButton.setText(_translate("instrumentSelection", "Refresh", None))
        __sortingEnabled = self.instrumentList.isSortingEnabled()
        self.instrumentList.setSortingEnabled(False)
        item = self.instrumentList.item(0)
        item.setText(_translate("instrumentSelection", "Detecting instruments....", None))
        self.instrumentList.setSortingEnabled(__sortingEnabled)
        self.okButton.setText(_translate("instrumentSelection", "OK", None))
        self.label.setText(_translate("instrumentSelection", "Select Instrument:", None))

