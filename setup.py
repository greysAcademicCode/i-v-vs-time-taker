from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need
# fine tuning.
buildOptions = dict(packages = ["scipy.sparse.csgraph","scipy.sparse.linalg"], excludes = ["tkinter"])
#build_exe_options = {"packages": ["os","scipy.integrate.lsoda","scipy.integrate.vode","scipy.sparse.linalg","scipy.special._ufuncs","scipy.sparse.csgraph","scipy.special","PyQt4.QtCore","PyQt4.QtGui","matplotlib.backends.backend_tkagg","matplotlib.backends.backend_qt4agg"], "excludes": ["tkinter"]}

import sys
base = 'Win32GUI' if sys.platform=='win32' else None

executables = [
    Executable('i-v-vs-time-taker.py', base=base,icon="icon.ico")
]

setup(name='i-v-vs-time-taker',
      version = '0.4',
      description = 'Helps capture transients during i-v curves',
      options = dict(build_exe = buildOptions),
      executables = executables)
