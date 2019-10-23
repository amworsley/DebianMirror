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
TF := azza/pool/main/l//linux-latest/linux-source_3.16+63+deb8u2_all.deb
azzatest: azza.cfg
	@if [ -e azza-updates ]; then \
	    @echo; echo " ** Cleaning old test away"; \
	    rm -rf azza-updates; \
	fi
	@echo; echo " ** Summary of azza.cfg configuration"
	./RepositoryMirror.py -c azza.cfg -info
	@echo; echo " ** Create local azza repository"
	./RepositoryMirror.py -c azza.cfg -create
	@echo; echo " ** Check local azza repository"
	./RepositoryMirror.py -c azza.cfg
	@echo; echo " ** Update azza repository"
	./RepositoryMirror.py -c azza.cfg -fetch
	@echo; echo " ** Check azza repository after sync"
	./RepositoryMirror.py -c azza.cfg
	@echo; echo " ** Remove test item and update"
	rm $(TF)
	./RepositoryMirror.py -c azza.cfg -fetch
	@if [ -r $(TF) ]; then \
	    echo; echo " ** Missing item retrieved!"; \
	else \
	    echo; echo " ** Missing NOT updated failed..."; \
	fi

stretchtest: stretchtest.cfg
	rm -rf stretchtest
	./RepositoryMirror.py -c stretchtest.cfg -info
	./RepositoryMirror.py -c stretchtest.cfg -create
	./RepositoryMirror.py -c stretchtest.cfg
	./RepositoryMirror.py -c stretchtest.cfg -fetch
	./RepositoryMirror.py -c stretchtest.cfg

buster-security-updates: buster-security-updates.cfg
	rm -rf buster-security-updates-test
	./RepositoryMirror.py -c buster-security-updates.cfg -info
	./RepositoryMirror.py -c buster-security-updates.cfg -create
	./RepositoryMirror.py -c buster-security-updates.cfg
	./RepositoryMirror.py -c buster-security-updates.cfg -fetch
	./RepositoryMirror.py -c buster-security-updates.cfg

buster-updates: buster-updates.cfg
	rm -rf buster-updates-test
	./RepositoryMirror.py -c buster-updates.cfg -info
	./RepositoryMirror.py -c buster-updates.cfg -create
	./RepositoryMirror.py -c buster-updates.cfg
	./RepositoryMirror.py -c buster-updates.cfg -fetch
	./RepositoryMirror.py -c buster-updates.cfg

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

