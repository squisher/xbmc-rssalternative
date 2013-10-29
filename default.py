#
#  Copyright 2012 (stieg), 2013 David Mohr "squisher"
#
#  This Program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2, or (at your option)
#  any later version.
#
#  This Program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; see the file COPYING.  If not, write to
#  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
#  http://www.gnu.org/copyleft/gpl.html
#


import xbmc,xbmcaddon,xbmcplugin,xbmcgui
import csv, urllib, urlparse, os, sys, urllib2
from xml.etree.ElementTree import ElementTree
import cPickle
from hashlib import sha1
import time

import rangereq

from common import *


sources = {}

for i in range(1,4):
  url = _settings_.getSetting('url'+str(i))
  if url:
    name = _settings_.getSetting('name'+str(i))
    if not name:
      name = url
    sources[name] = str(url)

print (_di_+ str(sources))

if not os.path.exists(_dataDir_):
  os.mkdir(_dataDir_)
if not os.path.exists(_tempDir_):
  os.mkdir(_tempDir_)

if os.path.exists(_lastCached_):
  fh = open(_lastCached_, 'rb')
  last_cached = cPickle.load(fh)
  fh.close()
else:
  last_cached = []

max_cached = int(_settings_.getSetting('nCached'))
def open_cache(f):
  global last_cached
  if f not in last_cached:
    if len(last_cached) > max_cached:
      last = last_cached[0]
      print(_di_+"Deleting cache " + last)
      os.unlink(last)
      last_cached = last_cached[1:]
    last_cached.append(f)
    fh = open(_lastCached_, 'wb')
    cPickle.dump(last_cached, fh)
    fh.close()

def url_query_to_dict(url):
  ''' Returns the URL query args parsed into a dictionary '''
  param = {}
  if url:
    u = urlparse.urlparse(url)
    for q in u.query.split('&'):
      kvp = q.split('=')
      param[kvp[0]] = kvp[1]

  return param


class Stream():
  def __init__(self, url):
    self.url = url
    self.started = False
    self.fully_cached = False
    self.chunk_len = 160*1024
    self.state_fn = os.path.join(_dataDir_, sha1(url).hexdigest())
    _, ext = os.path.splitext(url)
    if not ext:
      ext = '.stream'
    self.cache_fn = os.path.join(_tempDir_, sha1(url).hexdigest() + ext)
    print (_di_ + "url:   " + self.url)
    print (_di_ + "state: " + self.state_fn)
    print (_di_ + "cache: " + self.cache_fn)

    if os.path.exists(self.state_fn):
      f = open(self.state_fn)
      self.info = cPickle.loads(f.read())
      f.close()
      print (_di_+"Loading existing stream... (playback_pos=" + str(self.info['playback_pos']) + ")")
    else:
      self.info = {'url': self.url, 'playback_pos': 0.0, 'size': -1}
      print (_di_+"Loading new stream...")

  def restart(self):
    self.info['playback_pos'] = 0.0

  def resumable(self):
    return self.info['playback_pos'] > 0

  def isFullyCached(self):
    self.cache = open(self.cache_fn, 'ab')
    pos = self.cache.tell()
    self.cache.close()

    return pos == self.info['size']

  def start(self):
    self.started = True
    open_cache (self.cache_fn)
    self.cache = open(self.cache_fn, 'ab')
    pos = self.cache.tell()

    if pos == self.info['size']:
      self.fully_cached = True
      print (_di_+"Caching already done.")
      return

    req = urllib2.Request(self.url)

    if pos == 0:
      print (_di_+"Requesting whole file")

      self.instream = urllib2.urlopen(req)

      length = int(self.instream.headers['Content-Length'])
      if not length:
        print (_di_+self.instream.headers)
      self.info['size'] = length

      print (_di_+"Initial request, total length is " + str(length))

      data = self.instream.read(1024*1024)

    else:
      req.headers['Range'] = 'bytes=' + str(pos) + '-'
      print (_di_+"Requesting range " + req.headers['Range'])

      self.instream = urllib2.urlopen(req)

      data = self.instream.read(self.chunk_len)

    #print (_di_+"Caching " + str(len(data)) + " bytes")
    self.cache.write(data)

  def process(self):
    if self.fully_cached:
      xbmc.sleep(1000)
      return

    data = self.instream.read(self.chunk_len)
    #print (_di_+"Caching " + str(len(data)) + " bytes")
    self.cache.write(data)
    if data < self.chunk_len:
      print (_di_+"Caching is done!")
      self.fully_cached = True
      self.instream.close()
      self.cache.close()

  def stop(self, playback_pos=False):
    if not playback_pos is False:
      self.info['playback_pos'] = playback_pos
    if self.started:
      self.info['last_access'] = time.time()

    f = open(self.state_fn, 'w')
    f.write(cPickle.dumps(self.info))
    f.close()

    if self.started and not self.fully_cached:
      self.instream.close()
      self.cache.close()
    self.started = False


class StreamPlayer(xbmc.Player):
  def __init__(self, *args):
    super(xbmc.Player, self).__init__(*args)

  def _prepare(self, stream):
    self._stream = stream
    self._resumed = False

  def onPlaybackEnded (self, *args):
    print (_di_ + "Playback ended, position = " + str(self.getTime()))
    self._stream.stop(0)
    super (xbmc.Player, self).onPlaybackEnded(*args)

  def onPlayBackStarted (self):
    print (_di_ + "Playback started, used: " + str(self._resumed))
    pos = self._stream.info['playback_pos']
    if self._resumed and pos > 0:
      print (_di_ + "Seeking to " + str(pos))
      self.seekTime(pos)
    self._resumed = True

  def onPlayBackStopped (self, *args):
    try:
      t = self.getTime()
      self._stream.stop(t)
      print (_di_ + "Playback stopped, position = " + str(t))
    except RuntimeError, e:
      print (_di_+"Can't update the playback position!")
      print (_di_+str(e))
      self._stream.stop()
    self._resumed = False
    

def main():
  params = url_query_to_dict(sys.argv[2])
  
  src = params.get('src')
  url = params.get('url')
  if url:
    url = urllib.url2pathname(url)
  mode = params.get('mode')

  if url:
    # Play it.
    stream = Stream(url)

    if not mode:
      if stream.resumable():
        modes = ['resume']
        if stream.isFullyCached():
          # if we are fully cached, then we can seek anywhere
          modes.append('seek')
        else:
          # we can at least offer to restart if we can't seek
          modes.append('restart')
      else:
        modes = ['play']
      modes.append('about')

      for mode in modes:
        li = xbmcgui.ListItem(mode)
        u = sys.argv[0] + '?' + urllib.urlencode({'url':url, 'mode':mode})
        xbmcplugin.addDirectoryItem(handle = int(sys.argv[1]),
                                    url = u, listitem = li,
                                    isFolder = False)
      xbmcplugin.endOfDirectory(int(sys.argv[1]))

    elif mode == 'about':
      dialog = xbmcgui.Dialog()
      dialog.ok(stream.info['title'], stream.info['description'], stream.info['duration'], stream.info['pubdate'])
    else: # all other modes are handled here
      print (_di_ + "Playing url %s" % url)
      if mode == 'restart':
        stream.restart()
      elif mode == 'seek':
        dialog = xbmcgui.Dialog()
        hours = int(stream.info['playback_pos'] / 3600)
        minutes = int((stream.info['playback_pos'] % 3600) / 60)
        seek_to = dialog.numeric(2, "Jump to", "%02d:%02d"%(hours ,minutes))
        if seek_to:
          print (_di_+ "Manually seeking to " + seek_to)
          hours, minutes = seek_to.split(':')
          stream.info['playback_pos'] = (int(hours) * 3600) + (int(minutes) * 60)

      player = StreamPlayer()

      player._prepare(stream)
      stream.start()

      player.play(stream.cache_fn)
      while (player.isPlayingAudio()):
        # Keep script alive so that we can save the state when playing stops.
        #print (_di_+"Still playing...")
        stream.process()
        xbmc.sleep(1000)

      print (_di_ + "Bye!")


  elif src:
    print (_di_ + "Showing entries for " + src)

    data = urllib.urlopen(sources[src])
    tree = ElementTree()
    root = tree.parse(data)

    entries = root.findall('./channel/item')

    for i in range(len(entries)):
      f = entries[i]
      info = {
        'title': f.find('title'),
        'description': f.find('description'),
        'pubdate': f.find('pubDate'),
        'duration': f.find('itunes:duration', namespaces=dict(itunes='http://www.itunes.com/dtds/podcast-1.0.dtd')),
      }

      for k in info.keys():
        if info[k]:
          info[k] = info[k].text
        else:
          info[k] = ''

      url = f.find('enclosure').attrib['url']
      stream = Stream(url)
      stream.info.update(info)
      stream.stop()

      li = xbmcgui.ListItem(info['title'])

      #print (_di_ + str(info))
      u = sys.argv[0] + '?' + urllib.urlencode({'url': url})
      xbmcplugin.addDirectoryItem(handle = int(sys.argv[1]),
                                  url = u, listitem = li,
                                  isFolder = True)
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

  else:
    print(_di_ + "No source selected.")
    for k in sorted(sources.keys()):
      u = sys.argv[0] + "?src=" + k
      li = xbmcgui.ListItem(k)
      xbmcplugin.addDirectoryItem(handle = int(sys.argv[1]),
                                  url = u, listitem = li,
                                  isFolder = True)
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


main()
