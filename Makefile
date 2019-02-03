PREFIX=/usr/local/

.PHONY: help azzatest stretchtest
help:
	@echo "targets:"
	@echo "    tests fetch from local repository see config files for details"
	@echo "    smalltest - 1-2 minute test 4-5 file  fetches : azza-50.cfg"
	@echo "    azzatest - long 5 minute test full local repository fetch : azza.cfg"
	@echo "    install - copy $(IFILES) into $(INSTALL_PATH)"
	@echo "    diff - diff local RepositoryMirror.py with installed version"

lint: RepositoryMirror.py
	python3 -m py_compile $?

INSTALL_PATH := $(PREFIX)/bin
IFILES := RepositoryMirror.py update-rm.sh
install: $(IFILES)
	cp $? $(INSTALL_PATH)

clean:
	rm -rf azza-updates-50 azza-updates
diff-RepositoryMirror.py: $(INSTALL_PATH)/RepositoryMirror.py RepositoryMirror.py
	-diff -u $^

diff-update-rm.sh: $(INSTALL_PATH)/update-rm.sh update-rm.sh
	-diff -u $^

diff: diff-RepositoryMirror.py diff-update-rm.sh

# Check fast local mirror
azzatest: azza.cfg
	rm -rf azza-updates
	./RepositoryMirror.py -c azza.cfg -info
	./RepositoryMirror.py -c azza.cfg -create
	./RepositoryMirror.py -c azza.cfg
	./RepositoryMirror.py -c azza.cfg -fetch
	./RepositoryMirror.py -c azza.cfg

stretchtest: stretchtest.cfg
	rm -rf stretchtest
	./RepositoryMirror.py -c stretchtest.cfg -info
	./RepositoryMirror.py -c stretchtest.cfg -create
	./RepositoryMirror.py -c stretchtest.cfg
	./RepositoryMirror.py -c stretchtest.cfg -fetch
	./RepositoryMirror.py -c stretchtest.cfg

smalltest: azza-50.cfg
	echo "Testing -info"
	rm -rf azza-updates-50
	./RepositoryMirror.py -c azza-50.cfg -info
	echo
	echo " *** Testing -create *** "
	./RepositoryMirror.py -c azza-50.cfg -create
	echo
	echo " *** Testing default update *** "
	./RepositoryMirror.py -c azza-50.cfg
	echo
	echo " *** Testing -norefresh *** "
	./RepositoryMirror.py -c azza-50.cfg -norefresh
	echo
	echo " *** Testing -fetch *** "
	./RepositoryMirror.py -c azza-50.cfg -fetch
	echo
	echo " *** Testing azza-50-test.sh script tests *** "
	./azza-50-test.sh

# Need to move some unit tests into here
unittest:
	./TestRepositoryMirror.py -v

