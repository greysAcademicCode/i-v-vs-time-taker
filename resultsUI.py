# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'results.ui'
#
# Created: Tue Jan 21 11:02:02 2014
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

class Ui_results(object):
    def setupUi(self, results):
        results.setObjectName(_fromUtf8("results"))
        results.resize(635, 356)
        self.saveButton = QtGui.QPushButton(results)
        self.saveButton.setGeometry(QtCore.QRect(520, 310, 92, 27))
        self.saveButton.setObjectName(_fromUtf8("saveButton"))
        self.groupBox_8 = QtGui.QGroupBox(results)
        self.groupBox_8.setGeometry(QtCore.QRect(10, 290, 511, 51))
        self.groupBox_8.setCheckable(True)
        self.groupBox_8.setChecked(False)
        self.groupBox_8.setObjectName(_fromUtf8("groupBox_8"))
        self.lineEdit_5 = QtGui.QLineEdit(self.groupBox_8)
        self.lineEdit_5.setGeometry(QtCore.QRect(100, 20, 391, 27))
        self.lineEdit_5.setObjectName(_fromUtf8("lineEdit_5"))
        self.pushButton_2 = QtGui.QPushButton(self.groupBox_8)
        self.pushButton_2.setGeometry(QtCore.QRect(10, 20, 71, 27))
        self.pushButton_2.setObjectName(_fromUtf8("pushButton_2"))
        self.groupBox_2 = QtGui.QGroupBox(results)
        self.groupBox_2.setGeometry(QtCore.QRect(10, 230, 131, 51))
        self.groupBox_2.setCheckable(True)
        self.groupBox_2.setChecked(False)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.areaSpinBox = QtGui.QDoubleSpinBox(self.groupBox_2)
        self.areaSpinBox.setGeometry(QtCore.QRect(20, 20, 101, 22))
        self.areaSpinBox.setSingleStep(0.01)
        self.areaSpinBox.setProperty("value", 1.0)
        self.areaSpinBox.setObjectName(_fromUtf8("areaSpinBox"))
        self.summaryArea = QtGui.QTextBrowser(results)
        self.summaryArea.setGeometry(QtCore.QRect(10, 20, 256, 192))
        self.summaryArea.setObjectName(_fromUtf8("summaryArea"))
        self.label = QtGui.QLabel(results)
        self.label.setGeometry(QtCore.QRect(10, 0, 161, 17))
        self.label.setObjectName(_fromUtf8("label"))
        self.label_2 = QtGui.QLabel(results)
        self.label_2.setGeometry(QtCore.QRect(400, 130, 101, 17))
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.groupBox = QtGui.QGroupBox(results)
        self.groupBox.setGeometry(QtCore.QRect(170, 230, 301, 51))
        self.groupBox.setCheckable(True)
        self.groupBox.setChecked(False)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.ignore = QtGui.QSpinBox(self.groupBox)
        self.ignore.setGeometry(QtCore.QRect(20, 20, 71, 27))
        self.ignore.setMinimum(1)
        self.ignore.setMaximum(999999999)
        self.ignore.setObjectName(_fromUtf8("ignore"))

        self.retranslateUi(results)
        QtCore.QMetaObject.connectSlotsByName(results)

    def retranslateUi(self, results):
        results.setWindowTitle(_translate("results", "Sweep Results", None))
        self.saveButton.setText(_translate("results", "Save", None))
        self.groupBox_8.setStatusTip(_translate("results", "_<timestamp>.csv will be appended", None))
        self.groupBox_8.setTitle(_translate("results", "Autosave directory", None))
        self.pushButton_2.setText(_translate("results", "Browse", None))
        self.groupBox_2.setToolTip(_translate("results", "Not implimented", None))
        self.groupBox_2.setTitle(_translate("results", "Area Scaling", None))
        self.areaSpinBox.setSuffix(_translate("results", " cm^2", None))
        self.summaryArea.setHtml(_translate("results", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'Sans\'; font-size:10pt; font-weight:400; font-style:normal;\">\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"></p></body></html>", None))
        self.label.setText(_translate("results", "Results Summary:", None))
        self.label_2.setText(_translate("results", "Put a plot here", None))
        self.groupBox.setToolTip(_translate("results", "Not implimented", None))
        self.groupBox.setTitle(_translate("results", "Ignore data Xms after a voltage step", None))
        self.ignore.setSuffix(_translate("results", " ms", None))

