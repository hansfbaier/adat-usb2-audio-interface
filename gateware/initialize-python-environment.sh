#!/bin/bash
python3 -m venv venv
. venv/bin/activate
pip3 install -r requirements.txt
pip3 install git+https://github.com/m-labs/migen@3ffd64c9b47619bd6689b44f29a8ed7c74365f14
pip3 install git+https://github.com/enjoy-digital/litex@f9f1b8e25db6d6db1aa47a135a5f898c433d516e
pip3 install git+https://github.com/enjoy-digital/litedram@83d18f48c7f7590096ddb35d669836d7abb3be6f
pip3 install git+https://github.com/lambdaconcept/minerva
# we have to clone and manually install lambdasoc here, because pip3 has a problem with it
pushd /tmp
git clone https://github.com/lambdaconcept/lambdasoc.git
cd lambdasoc
pip3 install .
cd ..
rm -rf lambdasoc
popd
pushd venv/lib/python*/site-packages/lambdasoc/software/
git clone https://github.com/lambdaconcept/lambdasoc-bios.git bios
popd
