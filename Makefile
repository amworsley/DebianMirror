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

