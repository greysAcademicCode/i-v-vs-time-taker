from cx_Freeze import setup, Executable

import sys
base = 'Win32GUI' if sys.platform=='win32' else None

packages=['scipy', 'scipy.integrate', 'scipy.signal', 'numpy','scipy.sparse.linalg']

exe = Executable(
script="i-v-vs-time-taker.py",
base=base,
compress=True,
icon="icon.ico"
)

setup(name='i-v-vs-time-taker',
      version = '0.4',
      description = 'Helps capture transients during i-v curves',
      options = {"build_exe":{"packages":packages, "includes":["numpy", "scipy", "scipy.integrate" ,"scipy.sparse", "scipy.sparse.csgraph._validation"], "excludes":['collections._weakref','collections.sys','tk', '_tkagg', '_gtkagg', '_gtk', 'tcl']}},
      executables = [exe])
