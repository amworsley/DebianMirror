PREFIX=/usr/local/
lint: RepositoryMirror.py
	python3 -m py_compile $?

test:
	./RepositoryMirror.py -v

unittest:
	./TestRepositoryMirror.py -v

INSTALL_PATH := $(PREFIX)/bin
install: RepositoryMirror.py update-rm.sh
	cp $? $(INSTALL_PATH)

# Check fast local mirror
azzatest: azza.cfg
	rm -rf azza-updates
	./RepositoryMirror.py -c azza.cfg -info
	./RepositoryMirror.py -c azza.cfg -create
	./RepositoryMirror.py -c azza.cfg
	./RepositoryMirror.py -c azza.cfg -fetch
	./RepositoryMirror.py -c azza.cfg

smalltest: azza-50.cfg
	rm -rf azza-updates-50
	./RepositoryMirror.py -c azza-50.cfg -info
	./RepositoryMirror.py -c azza-50.cfg -create
	./RepositoryMirror.py -c azza-50.cfg
	./RepositoryMirror.py -c azza-50.cfg -norefresh
	./RepositoryMirror.py -c azza-50.cfg -fetch
	./RepositoryMirror.py -c azza-50.cfg
	./azza-50-test.sh
