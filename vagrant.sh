#!/usr/bin/env bash
# Configuration
INSTALLDIR=/home/vagrant/pyex

# System Maintenance
apt-get update
apt-get -y upgrade

# Dependencies
apt-get -y install git
apt-get -y install python3
apt-get -y install graphviz graphviz-dev

## Z3
apt-get -y install g++
apt-get -y install make
apt-get -y install python3-examples
cd /tmp
git clone https://github.com/Z3Prover/z3.git
cd z3
python3 scripts/mk_make.py
cd build
make
mkdir /usr/lib/python3/dist-packages/__pycache__
make install
cd

## CVC4
apt-get install -y libgmp-dev
apt-get install -y libboost-all-dev
apt-get install -y openjdk-7-jre openjdk-7-jdk
apt-get install -y swig
apt-get install -y python3-dev
apt-get install -y autoconf
cd /tmp
git clone https://github.com/CVC4/CVC4.git
cd CVC4
./autogen.sh
contrib/get-antlr-3.4
export PYTHON_CONFIG=/usr/bin/python3-config
./configure --enable-optimized --with-antlr-dir=/tmp/CVC4/antlr-3.4 ANTLR=/tmp/CVC4/antlr-3.4/bin/antlr3 \
  --enable-language-bindings=python
echo "python_cpp_SWIGFLAGS = -py3" >> src/bindings/Makefile.am
autoreconf
make
make install
echo "/usr/local/lib" > /etc/ld.so.conf.d/cvc4.conf
/sbin/ldconfig
cp builds/src/bindings/python/CVC4.py /usr/lib/python3/dist-packages/CVC4.py
cp builds/src/bindings/python/.libs/CVC4.so /usr/lib/python3/dist-packages/_CVC4.so
cd

# Z3-str2
apt-get install -y unzip
apt-get install -y dos2unix
cd /tmp
git clone https://github.com/GroundPound/Z3-str.git
cd Z3-str/
DOWNLOAD_URL="http://download-codeplex.sec.s-msft.com/Download/Release?ProjectName=z3&DownloadId=500120&"
DOWNLOAD_URL+="FileTime=129936928520170000&Build=21031"
curl -o z3.zip -L ${DOWNLOAD_URL}
unzip z3.zip
cp z3.patch z3/
cd z3
patch -p0 < z3.patch
autoconf
./configure
make
make a
cd ..
sed -i 's#Z3_path = #Z3_path =/tmp/Z3-str/z3#' Makefile
make
sed -i 's#solver = ""#solver = "/opt/z3-str/str"#' Z3-str.py
chmod a+x str
chmod a+x Z3-str.py
mkdir /opt/z3-str
cp Z3-str.py /opt/z3-str/.
cp str /opt/z3-str/.
ln -s /opt/z3-str/Z3-str.py /usr/bin/z3-str

# Z3-str2 Support
apt-get -y install python3-pip
pip-3.2 install sexpdata

# PyEx Dependencies
pip3 install sexpdata

## Integer Linear Programming Tools
apt-get install -y libatlas-base-dev gfortran
apt-get install -y python3-dev
apt-get install -y python3-numpy python3-scipy
pip3 install cvxopt
pip3 install cvxpy


# Installation
ln -s /vagrant ${INSTALLDIR}
ln -s ${INSTALLDIR}/symbolic /usr/lib/python3/dist-packages/
cat > /usr/bin/pyex <<EOF
#/bin/sh
PYTHONPATH=\$PYTHONPATH:"\$(pwd)" python3 -OO ${INSTALLDIR}/pyexz3.py \$*
EOF
chmod a+x /usr/bin/pyex

# Tests
cd ${INSTALLDIR}
python3 run_tests.py test
