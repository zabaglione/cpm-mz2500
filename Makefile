PYTHON ?= python3

all: disks

# CP/M sources, DRI utilities, the console font and the language
# suites (all SHA256-pinned)
fetch:
	$(PYTHON) tools/fetch_cpm22.py
	$(PYTHON) tools/fetch_tools.py

disks:
	$(PYTHON) tools/make_boot_d88.py --output build/cpm_boot.d88
	$(PYTHON) tools/make_boot_d88.py --data-disk --output build/cpm_data.d88
	$(PYTHON) tools/make_hdd_image.py --output build/cpm.hdd
	$(PYTHON) tools/make_boot_d88.py --collection tools --output build/cpm_tools.d88
	$(PYTHON) tools/make_boot_d88.py --collection langs1 --output build/cpm_langs1.d88
	$(PYTHON) tools/make_boot_d88.py --collection langs2 --output build/cpm_langs2.d88

test:
	$(PYTHON) -m unittest discover -s tests

clean:
	rm -rf build

.PHONY: all fetch disks test clean
