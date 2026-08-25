PYTHON ?= python3

all: disks

# CP/M sources, DRI utilities and the console font (SHA256-pinned)
fetch:
	$(PYTHON) tools/fetch_cpm22.py

disks:
	$(PYTHON) tools/make_boot_d88.py --output build/cpm_boot.d88
	$(PYTHON) tools/make_boot_d88.py --data-disk --output build/cpm_data.d88
	$(PYTHON) tools/make_hdd_image.py --output build/cpm.hdd

test:
	$(PYTHON) -m unittest discover -s tests

clean:
	rm -rf build

.PHONY: all fetch disks test clean
