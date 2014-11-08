#!/usr/bin/env python
import webapp2
import cgi
import time
import os
import jinja2
import urllib
import cloudstorage as gcs
import urlparse
from google.appengine.ext.webapp import template
from google.appengine.api import users
from google.appengine.api import app_identity
from google.appengine.api import memcache

from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers



############################## GLOBAL PARAMETERS #############################
my_default_retry_params = gcs.RetryParams(initial_delay=0.2,
										  max_delay=5.0,
										  backoff_factor=2,
										  max_retry_period=15)
write_retry_params = gcs.RetryParams(backoff_factor=1.1)
bucket = '/cloudcomputing553'

############################# FUNCTIONS #################################

#Insert a file in GCS bucket
def insert(key, value):
	try:
		gcs_file = gcs.open(key,
							'w',
		    		        content_type='text/plain',
			    			retry_params=write_retry_params)
		gcs_file.write(value)
		gcs_file.close()
		return True
	except Exception:
		return False
			
#Insert a file in cache (the file stays in cache for 24 hours)
def insertCache(key, value):
	if key is None:
		return False
	if not memcache.set(key, value, 86400):
		return False
	return True

#Check if a file is in GCS bucket
def check(key):
	try:
		gcs.stat(key,
		 	 	 retry_params=write_retry_params)
		return True
	except Exception:
		return False
			
#Check if a file is in memcache
def checkCache(key):
	if memcache.get(key) is None:
		return False
	return True

#Retrieve the content of a file in GCS
def find(key):
	try:
		gcs_file = gcs.open(key,'r')
		data = gcs_file.read()
		gcs_file.close()
		return data
	except Exception:
		return 'Name of file invalid, file does not exist or problem with reading the file'
			
#Get file contents from memcache
def findCache(key):
	if key is None:
		return 'File does not exist'
	value = memcache.get(key)
	return value

#Remove a file from GCS bucket
def remove(key):
	filename = bucket + '/' + key
	try:
		gcs.delete(filename,
				   retry_params=None)
		if checkCache(key): removeCache(key)
		return True
	except Exception:
		return False

#Remove a file from memcache
def removeCache(key):
	if key is None:
		return False
	if memcache.delete(key) != 2:
		return False
	return True

#Remove all files from the cache and GCS bucket
def removeAll():
	#removeAllCache()
	
	content = listing()
	for i in content:
		if not remove(str(i).replace(bucket,"")[1:]): return False
	removeAllCache()
	return True

#Remove all cache
def removeAllCache():	
	if memcache.flush_all():
		return True
	else:
		return False

#List all elements in GCS bucket
def listing():
	listbucket=[]
	bucketContent = gcs.listbucket(bucket,
				 				   marker=None,
				 				   max_keys=None,
				  				   delimiter=None,
				  				   retry_params=None)
	for entry in bucketContent:
		listbucket.append(entry.filename)
	return listbucket

def cacheSizeMB():
	return float(memcache.get_stats()['bytes']) / 1024

def cacheSizeElem():
	return memcache.get_stats()['items']

################################## PAGES #####################################

#This is the main page. It has a dropdown menu where one can choose between
#multiple options.
class MainPage(webapp2.RequestHandler):
	def get(self):
		template_values = {}
		path = os.path.join(os.path.dirname(__file__), "form.html")
		self.response.write(template.render(path,template_values))

#This is the page showed to the user after he picked one of the
#options.For example, if the user chose 'Insert file' he will
#get the menu to look for a file to upload into GCS bucket.
class Landing(webapp2.RequestHandler):
	def post(self):
		global opt
		JINJA_ENVIRONMENT = jinja2.Environment(
    	loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    	extensions=['jinja2.ext.autoescape'],
    	autoescape=True)

		opt = cgi.escape(self.request.get('opt'))			
		
		template_values = {
            'option': opt
		}
		
		template = JINJA_ENVIRONMENT.get_template('landing.html.jinja2')
		self.response.write(template.render(template_values))				

#This page will choose among the below classes and execute the
#right function. 
class Process(webapp2.RequestHandler):
	def get(self):
		JINJA_ENVIRONMENT = jinja2.Environment(
    	loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    	extensions=['jinja2.ext.autoescape'],
    	autoescape=True)
		
		option = self.request.get('option')
		success = self.request.get('success')
		elements = self.request.get('elements')
		size = self.request.get('size')

		template_values = {
            'option': option,
			'success' : success,
			'elements': elements,
			'size': size
		}

		template = JINJA_ENVIRONMENT.get_template('process.html.jinja2')
		self.response.write(template.render(template_values))


class Insert(webapp2.RequestHandler):
	def post(self):
		key = self.request.get('insert')
		key = key.encode()
		f = open(key)
		value = f.read()
		f.close()
		success = 'yes'
		filename = bucket + '/' + key
		if(len(value)<=100000): #If the size of the file is < 100 kb, we
		#add it to the cache as well
			if not insertCache(key, value) : success = 'no'
		if not insert(filename, value) : success = 'no'

		redirect_url = "process?option=insert&success=%s" % success		
		self.redirect(redirect_url)

		
class Check(webapp2.RequestHandler):
	def post(self):
		key = self.request.get('check')
		success = 'yes'
		filename = bucket + '/' + key
		if not checkCache(key):
			if not check(filename): success = 'no'

		redirect_url = "process?option=check&success=%s" % success		
		self.redirect(redirect_url)

class Find(webapp2.RequestHandler):
	def post(self):
		key = self.request.get('find')
		success = 'yes'
		filename = bucket + '/' + key
		data = findCache(key)
		if (data is None):
			if check(filename):
				data = find(filename)
			else:
				success = 'no'
		self.response.write(data)
		#redirect_url = "process?option=find&success=%s" % success
		#self.redirect(redirect_url)
		

class Remove(webapp2.RequestHandler):
	def post(self):

		key = self.request.get('remove')
		filename = bucket + '/' + key
		success = 'yes'

		if not removeCache(key) and checkCache(key): success = 'no'
		if not remove(key) and check(filename): success = 'no'

		redirect_url = "process?option=remove&success=%s" % success
		self.redirect(redirect_url)

class RemoveAll(webapp2.RequestHandler):
	def get(self):
		success = 'yes'
		if not removeAll(): success = 'no'
		redirect_url = "process?option=removeall&success=%s" % success		
		self.redirect(redirect_url)


class Listing(webapp2.RequestHandler):
	def get(self):
		self.response.write("Listing of elements in bucket <b>%s</b> :<br/>" % bucket[1:])
		listbucket = listing()
		for s in listbucket:
			self.response.write("<br/>")
			self.response.write(str(s).replace(bucket,"")[1:])

class CheckCache(webapp2.RequestHandler):
	def post(self):
		key = self.request.get('checkcache')
		success = 'yes'
		if not checkCache(key): success = 'no'

		redirect_url = "process?option=checkcache&success=%s" % success		
		self.redirect(redirect_url)

class RemoveAllCache(webapp2.RequestHandler):
	def get(self):
		success = 'yes'
		if not removeAllCache(): success = 'no'

		redirect_url = "process?option=removeallcache&success=%s" % success		
		self.redirect(redirect_url)

class CacheSize(webapp2.RequestHandler):
	def get(self):
		success = 'yes'
		size = cacheSizeMB()
		redirect_url = "process?option=cachesize&success=%s&size=%s" % (success, size)
		self.redirect(redirect_url)

class CacheSizeElem(webapp2.RequestHandler):
	def get(self):
		success = 'yes'
		items = cacheSizeElem()
		redirect_url = "process?option=cachesizeelem&success=%s&elements=%s" % (success, items)
		self.redirect(redirect_url)
'''
class Insert_Blob(blobstore_handlers.BlobstoreUploadHandler):

	def post(self):
		upload_files = self.get_uploads('browse')  
		blob_info = upload_files[0]
		self.redirect('/')
		#self.redirect('/serve/%s' % blob_info.key())

class Landing_(webapp2.RequestHandler):

	def post(self):

		JINJA_ENVIRONMENT = jinja2.Environment(
    	loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    	extensions=['jinja2.ext.autoescape'],
    	autoescape=True)

		opt = cgi.escape(self.request.get('opt'))
		upload_url = blobstore.create_upload_url('/insert')
		
		template_values = {
            'option': opt,
			'upload' : upload_url
		}
		
		template = JINJA_ENVIRONMENT.get_template('landing.html.jinja2')
		self.response.write(template.render(template_values))
'''


app = webapp2.WSGIApplication([
    ('/', MainPage),
	('/land', Landing),
	('/process', Process),
	('/insert', Insert_Blob),
	('/check', Check),
	('/find', Find),
	('/remove', Remove),
	('/removeall', RemoveAll),
	('/listing', Listing),
	('/checkcache', CheckCache),
	('/removeallcache', RemoveAllCache),
	('/cachesize', CacheSize),
	('/cachesizeelem', CacheSizeElem)
], debug=True)


