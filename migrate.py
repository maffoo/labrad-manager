"""
Migrate labrad registry from the old delphi format.

This works by traversing the existing registry files
on disk, and then making registry calls to the new
registry location in a running manager. Hence, while
this requires knowledge of the old delphi file format,
we use only the registry labrad api of the new registry
and avoid tying ourselves to the new on-disk registry
format.
"""

import os
import sys
import time

import labrad
import labrad.types as T

from delphi_compat import string_to_data
from registry import decode_filename

def migrate(cxn, root):
	t_start = time.time()

	reg = cxn.registry
	for dirpath, dirnames, filenames in os.walk(root):
		relpath = os.path.relpath(dirpath, root)

		# compute the registry path
		regpath = []
		path = dirpath
		while path != root:
			path, dirname = os.path.split(path)
			regpath.insert(0, decode_filename(dirname[:-4]))
		regpath.insert(0, '')
		print regpath,

		reg.cd(regpath, True)
		_, existing_keys = reg.dir()

		if len(existing_keys) == len(filenames):
			print '** skip **'
			continue

		t0 = time.time()
		pkt = reg.packet()
		pkt.cd(regpath, True)
		for fname in filenames:
			key = decode_filename(fname[:-4])
			with open(os.path.join(dirpath, fname)) as f:
				s = f.read()
				value = string_to_data(s)
				T.flatten(value)
				pkt.set(key, value)
		t1 = time.time()
		pkt.send()
		t2 = time.time()

		print 'load: {0}, save: {1}'.format(
			int((t1-t0)*1000),
			int((t2-t1)*1000)
		)

	t_end = time.time()
	elapsed = int(t_end - t_start)
	h, ms = divmod(elapsed, 3600)
	m, s = divmod(ms, 60)

	print 'elapsed: {h}:{m:02}:{s:02}'.format(h=h, m=m, s=s)

if __name__ == '__main__':
	root = sys.argv[1]
	print 'migrating registry from {}'.format(root)
	with labrad.connect() as cxn:
		migrate(cxn, root)
