from cx_Freeze import setup, Executable
import scipy
import sys
base = 'Win32GUI' if sys.platform=='win32' else None

packages=['scipy', 'scipy.integrate', 'scipy.signal', 'numpy','scipy.sparse.linalg','scipy.optimize','scipy.optimize.minpack2',"os","scipy.integrate.lsoda","scipy.integrate.vode","scipy.sparse.linalg","scipy.special._ufuncs","scipy.sparse.csgraph","scipy.special","PyQt4.QtCore","PyQt4.QtGui","matplotlib.backends.backend_tkagg","matplotlib.backends.backend_qt4agg"]

exe = Executable(
script="i-v-vs-time-taker.py",
base=base,
compress=True,
icon="icon.ico"
)

setup(name='i-v-vs-time-taker',
      version = '0.4',
      description = 'Helps capture transients during i-v curves',
      options = {"build_exe":{"packages":packages, "includes":["numpy", "scipy", 'scipy.optimize','scipy.optimize.minpack2', "scipy.integrate" ,"scipy.sparse", "scipy.sparse.csgraph._validation"], "excludes":['tcl','tkinter','collections._weakref','collections.sys','tk', '_tkagg', '_gtkagg', '_gtk', 'tcl']}},
      executables = [exe])
