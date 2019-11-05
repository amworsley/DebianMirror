PREFIX=/usr/local/

.PHONY: help jessietest stretchtest bustertest buster-updates-test buster-security-test
.PHONY: bullseye-test
help:
	@echo "targets:"
	@echo "    tests fetch from local repository see config files for details"
	@echo "    smalltest - 1-2 minute test 4-5 file  fetches : azza-50.cfg"
	@echo "    jessietest - long 5 minute test full local repository fetch : azza.cfg"
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
TF := jessie-updates/pool/main/l//linux-latest/linux-source_3.16+63+deb8u2_all.deb
jessietest: jessie.cfg
	@if [ -e jessie-updates ]; then \
	    @echo; echo " ** Cleaning old test away"; \
	    rm -rf jessie-updates; \
	fi
	@echo; echo " ** Summary of jessie.cfg configuration"
	./RepositoryMirror.py -c jessie.cfg -info
	@echo; echo " ** Create local jessie repository"
	./RepositoryMirror.py -c jessie.cfg -create
	@echo; echo " ** Check local jessie repository"
	./RepositoryMirror.py -c jessie.cfg
	@echo; echo " ** Update jessie repository"
	./RepositoryMirror.py -c jessie.cfg -fetch
	@echo; echo " ** Check jessie repository after sync"
	./RepositoryMirror.py -c jessie.cfg
	@echo; echo " ** Remove test item and update"
	rm $(TF)
	./RepositoryMirror.py -c jessie.cfg -fetch
	@if [ -r $(TF) ]; then \
	    echo; echo " ** Missing item retrieved!"; \
	else \
	    echo; echo " ** Missing NOT updated failed..."; \
	fi

STF := stretchtest/pool/main/e/exim4/exim4-config_4.89-2+deb9u5_all.deb
stretchtest: stretchtest.cfg
	@if [ -e stretchtest ]; then \
	    @echo; echo " ** Cleaning old test away"; \
	    rm -rf stretchtest; \
	fi
	@echo; echo " ** Summary of stretchtest.cfg configuration"
	./RepositoryMirror.py -c stretchtest.cfg -info
	@echo; echo " ** Create local azza repository"
	./RepositoryMirror.py -c stretchtest.cfg -create
	@echo; echo " ** Check local azza repository"
	./RepositoryMirror.py -c stretchtest.cfg
	@echo; echo " ** Update azza repository"
	./RepositoryMirror.py -c stretchtest.cfg -fetch
	@echo; echo " ** Check azza repository after sync"
	./RepositoryMirror.py -c stretchtest.cfg
	@echo; echo " ** Remove test item $(STF) and update"
	rm $(STF)
	./RepositoryMirror.py -c stretchtest.cfg -fetch
	@if [ -r $(STF) ]; then \
            echo; echo " ** Missing item retrieved!"; \
	else \
	    echo; echo " ** Missing NOT updated failed..."; \
	fi


buster-security-updates: buster-security-updates.cfg
	rm -rf buster-security-updates-test
	./RepositoryMirror.py -c buster-security-updates.cfg -info
	./RepositoryMirror.py -c buster-security-updates.cfg -create
	./RepositoryMirror.py -c buster-security-updates.cfg
	./RepositoryMirror.py -c buster-security-updates.cfg -fetch
	./RepositoryMirror.py -c buster-security-updates.cfg

BTF := bustertest/pool/main/j/java-common/default-jre_1.11-71_amd64.deb
bustertest: bustertest.cfg
	@if [ -e bustertest ]; then \
	    @echo; echo " ** Cleaning old test away"; \
	    rm -rf bustertest; \
	fi
	@echo; echo " ** Summary of bustertest.cfg configuration"
	./RepositoryMirror.py -c bustertest.cfg -info
	@echo; echo " ** Create local azza repository"
	./RepositoryMirror.py -c bustertest.cfg -create
	@echo; echo " ** Check local azza repository"
	./RepositoryMirror.py -c bustertest.cfg
	@echo; echo " ** Update azza repository"
	./RepositoryMirror.py -c bustertest.cfg -fetch
	@echo; echo " ** Check azza repository after sync"
	./RepositoryMirror.py -c bustertest.cfg
	@echo; echo " ** Remove test item and update"
	rm $(BTF)
	./RepositoryMirror.py -c bustertest.cfg -fetch
	@if [ -r $(BTF) ]; then \
            echo; echo " ** Missing item retrieved!"; \
	else \
	    echo; echo " ** Missing NOT updated failed..."; \
	fi

BUTF := buster-updates-test/pool/main/t/tzdata/tzdata_2019c-0+deb10u1_all.deb
buster-updates-test: buster-updates-test.cfg
	@if [ -e buster-updates-test ]; then \
	    @echo; echo " ** Cleaning old test away"; \
	    rm -rf buster-updates-test; \
	fi
	@echo; echo " ** Summary of buster-updates-test.cfg configuration"
	./RepositoryMirror.py -c buster-updates-test.cfg -info
	@echo; echo " ** Create local azza repository"
	./RepositoryMirror.py -c buster-updates-test.cfg -create
	@echo; echo " ** Check local azza repository"
	./RepositoryMirror.py -c buster-updates-test.cfg
	@echo; echo " ** Update azza repository"
	./RepositoryMirror.py -c buster-updates-test.cfg -fetch
	@echo; echo " ** Check azza repository after sync"
	./RepositoryMirror.py -c buster-updates-test.cfg
	@echo; echo " ** Remove test item and update"
	rm $(BUTF)
	./RepositoryMirror.py -c buster-updates-test.cfg -fetch
	@if [ -r $(BUTF) ]; then \
            echo; echo " ** Missing item retrieved!"; \
	else \
	    echo; echo " ** Missing NOT updated failed..."; \
	fi
	rm -rf buster-updates-test

BSTF := buster-security-test/pool/updates/main/f/firefox-esr/iceweasel-l10n-az_68.2.0esr-1~deb10u1_all.deb
buster-security-test: buster-security-test.cfg
	@if [ -e buster-security-test ]; then \
	    @echo; echo " ** Cleaning old test away"; \
	    rm -rf buster-security-test; \
	fi
	@echo; echo " ** Summary of buster-security-test.cfg configuration"
	./RepositoryMirror.py -c buster-security-test.cfg -info
	@echo; echo " ** Create local azza repository"
	./RepositoryMirror.py -c buster-security-test.cfg -create
	@echo; echo " ** Check local azza repository"
	./RepositoryMirror.py -c buster-security-test.cfg
	@echo; echo " ** Update azza repository"
	./RepositoryMirror.py -c buster-security-test.cfg -fetch
	@echo; echo " ** Check azza repository after sync"
	./RepositoryMirror.py -c buster-security-test.cfg
	@echo; echo " ** Remove test item and update"
	rm $(BSTF)
	./RepositoryMirror.py -c buster-security-test.cfg -fetch
	@if [ -r $(BSTF) ]; then \
            echo; echo " ** Missing item retrieved!"; \
	else \
	    echo; echo " ** Missing NOT updated failed..."; \
	fi
	rm -rf buster-security-test

BETF := bullseye-test/pool/main/e/emacs/emacs-bin-common_26.1+1-4_amd64.deb
bullseye-test: bullseye-test.cfg
	@if [ -e bullseye-test ]; then \
	    @echo; echo " ** Cleaning old test away"; \
	    rm -rf bullseye-test; \
	fi
	@echo; echo " ** Summary of bullseye-test.cfg configuration"
	./RepositoryMirror.py -c bullseye-test.cfg -info
	@echo; echo " ** Create local azza repository"
	./RepositoryMirror.py -c bullseye-test.cfg -create
	@echo; echo " ** Check local azza repository"
	./RepositoryMirror.py -c bullseye-test.cfg
	@echo; echo " ** Update azza repository"
	./RepositoryMirror.py -c bullseye-test.cfg -fetch
	@echo; echo " ** Check azza repository after sync"
	./RepositoryMirror.py -c bullseye-test.cfg
	@echo; echo " ** Remove test item and update"
	rm $(BETF)
	./RepositoryMirror.py -c bullseye-test.cfg -fetch
	@if [ -r $(BETF) ]; then \
            echo; echo " ** Missing item retrieved!"; \
	else \
	    echo; echo " ** Missing NOT updated failed..."; \
	fi
	rm -rf bullseye-test

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

