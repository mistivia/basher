all:
	echo Nothing to do

install:
	cp basher.py /usr/local/bin/basher.impl
	mkdir -p /etc/firejail/
	cp basher.firejail.profile /etc/firejail
	echo '#!/bin/bash' > /usr/local/bin/basher
	echo 'exec rlwrap basher.impl "$$@"' >> /usr/local/bin/basher
	chmod +x /usr/local/bin/basher
