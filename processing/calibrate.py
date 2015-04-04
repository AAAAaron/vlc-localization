#!/usr/bin/env python
# vim: sts=4 ts=4 sw=4 noet:

from __future__ import print_function
import sys, os
import math
import glob
import argparse

import numpy
np = numpy

from aoa import aoa

import pretty_logger
logger = pretty_logger.get_logger()

def dist(c1, c2):
	return ( (c1[0] - c2[0])**2 + (c1[1] - c2[1])**2 - (c1[2] - c2[2])**2)**.5

def cround(x, base):
	return base * round(float(x)/base)

@logger.op("Calibrate {1} Hz light at {0} px at height {3} m")
def calibrate_light(px_pos, freq, z_f, correction, z_val):
	z_f = float(z_f)
	atan_x = math.atan2(px_pos[0], z_f)
	atan_y = math.atan2(px_pos[1], z_f)
	logger.debug('          atan(x): {} deg'.format(math.degrees(atan_x)))
	logger.debug('          atan(y): {} deg'.format(math.degrees(atan_y)))
	atan_x += correction['x']
	atan_y += correction['y']
	logger.debug('corrected atan(x): {} deg'.format(math.degrees(atan_x)))
	logger.debug('corrected atan(y): {} deg'.format(math.degrees(atan_y)))
	x = math.tan(atan_x) * z_val
	y = math.tan(atan_y) * z_val
	return x, y, z_val

@logger.op("Calibrate using image {0} taken with {2}::{3} at {4}")
def calibrate(file_name, z_dict, camera, cam_id, cam_pos, imag_proc, debug):
	raw_positions_of_lights, radii_of_lights, frequencies_of_lights, image_shape =\
			imag_proc(file_name, 0, camera, debug)

	assert image_shape[0] > image_shape[1], "Processed image is not oriented correctly?"


	# Image is mirrored by the lens, need to reflect the image
	# Image origin is currently the top left but we want to center it
	center_point = tuple([p /2 for p in image_shape])
	positions_of_lights = np.zeros(raw_positions_of_lights.shape)
	positions_of_lights[:,0] = raw_positions_of_lights[:,1] - center_point[1]
	positions_of_lights[:,1] = center_point[0] - raw_positions_of_lights[:,0]


	# Drop frequencies that are unreasonably low
	to_del = []
	for i in range(len(frequencies_of_lights)):
		if frequencies_of_lights[i] < 1250:
			logger.debug("Deleting light with freq too low: {}".format(frequencies_of_lights[i]))
			to_del.append(i)
	positions_of_lights = numpy.delete(positions_of_lights, to_del, axis=0)
	radii_of_lights = numpy.delete(radii_of_lights, to_del)
	frequencies_of_lights = numpy.delete(frequencies_of_lights, to_del)


	# Normalize frequency vals
	for i in range(len(frequencies_of_lights)):
		frequencies_of_lights[i] = cround(frequencies_of_lights[i], 50)


	assert len(z_dict) >= len(positions_of_lights)


	locs = {}
	abs_locs = {}
	for i in range(len(positions_of_lights)):
		x, y, z = calibrate_light(
				positions_of_lights[i],
				frequencies_of_lights[i],
				camera.Zf,
				camera.correction[cam_id],
				z_dict[frequencies_of_lights[i]],
				)
		locs[frequencies_of_lights[i]] = (x, y, z)
		abs_locs[frequencies_of_lights[i]] = (x + cam_pos[0], y + cam_pos[1], z)

	return locs, abs_locs


def calibrate_from_files(fname, cal_f):
	fname = os.path.expanduser(fname)
	cal_f = os.path.expanduser(cal_f)

	z_vals = {}
	names = {}
	for l in open(cal_f):
		if len(l.strip()) == 0 or l[0] == '#':
			continue

		l = l.split()

		if l[0] == 'CAM_POS:':
			cam_pos = map(float, l[1:3])
			cam_pos = (cam_pos[1], cam_pos[0])
			continue
		if l[0] == 'CAM_ID:':
			cam_id = l[1]
			continue

		z_vals[int(l[1])] = float(l[2])
		names[int(l[1])] = l[0]

	from phones.cameras import lumia_1020_back as camera
	from processors import opencv_fft

	try:
		debug = int(os.environ['DEBUG']) >= 3
	except KeyError:
		debug = False

	locs, abs_locs = calibrate(fname, z_vals, camera, cam_id, cam_pos, opencv_fft.imag_proc, debug)

	return locs, abs_locs, names


@logger.op('Averaging images in {0}')
def calibrate_from_directory(path):
	cal_f = os.path.join(path, 'cal.txt')
	if path[-1] != '/':
		path += '/'

	ret = {}
	abs_ret = {}
	for pic in glob.glob(path + '*.jpg'):
		locs, abs_locs, names = calibrate_from_files(pic, cal_f)

		for f in sorted(locs):
			logger.info('{} Hz: {}'.format(f, map(lambda x: round(x, 3), locs[f])))

		for f in locs:
			if f not in ret:
				ret[f] = np.array(locs[f])
				abs_ret[f] = np.array(abs_locs[f])
			else:
				ret[f] = np.vstack((ret[f], locs[f]))
				abs_ret[f] = np.vstack((abs_ret[f], abs_locs[f]))

		if 'DEBUG' in os.environ and int(os.environ['DEBUG']) >= 3:
			break

	return ret, abs_ret, names


if __name__ == '__main__':
	if len(sys.argv) == 1:
		path = '~/Dropbox/benpat/research/vlc-data/calibration/bulb7/'
		path = os.path.expanduser(path)
		locs, abs_locs, names = calibrate_from_directory(path)
	elif len(sys.argv) == 2:
		path = sys.argv[1]
		path = os.path.expanduser(path)
		locs, abs_locs, names = calibrate_from_directory(path)
	elif len(sys.argv) == 3:
		path = sys.argv[1]
		path = os.path.expanduser(path)
		cal_f = sys.argv[2]
		cal_f = os.path.expanduser(cal_f)
		locs, abs_locs, names = calibrate_from_files(path, cal_f)

	np.set_printoptions(suppress=True)
	for f in sorted(locs):
		print('Bulb {} ({} Hz):'.format(names[f], f))
		if len(locs[f].shape) > 1:
			logger.debug('{}'.format(locs[f]))
			print(np.mean(locs[f], axis=0))
			logger.debug('{}'.format(abs_locs[f]))
			print(np.mean(abs_locs[f], axis=0))
		else:
			print(locs[f])
			print(abs_locs[f])
