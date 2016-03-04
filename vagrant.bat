@powershell -NoProfile -ExecutionPolicy unrestricted -Command ^
"(iex ((new-object net.webclient).DownloadString('https://chocolatey.org/install.ps1'))) >$null 2>&1" ^
&& SET PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin
choco install -y python3
choco install -y graphviz
choco install -y curl
choco install -y git.install -params '"/GitAndUnixToolsOnPath"'
SET PATH=%PATH%;C:\Program Files (x86)\Git\bin

cd %TEMP%
curl "https://github.com/Z3Prover/bin/raw/master/releases/z3-4.4.0-x64-win.zip" --compressed -L -o z3-4.4.0-x64-win.zip
unzip z3-4.4.0-x64-win.zip
mv z3-4.4.0-x64-win C:\z3
cd C:\z3\bin
FOR %%c in (z3*.py) DO C:\tools\python3\python C:\tools\python3\Tools\Scripts\reindent.py %%c
