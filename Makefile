lint: RepositoryMirror.py
	python3 -m py_compile $?

test:
	./RepositoryMirror.py -v

unittest:
	./TestRepositoryMirror.py -v
