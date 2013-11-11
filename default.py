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
  # compatability: 0.2.0 used to store the full path, now it's only the basename
  last_cached = [os.path.basename(s) for s in cPickle.load(fh)]
  fh.close()
else:
  last_cached = []

max_cached = int(_settings_.getSetting('nCached'))

def url_query_to_dict(url):
  ''' Returns the URL query args parsed into a dictionary '''
  param = {}
  if url:
    u = urlparse.urlparse(url)
    for q in u.query.split('&'):
      kvp = q.split('=')
      param[kvp[0]] = kvp[1]

  return param

def time_str2secs(s):
  hms = s.split(':')
  if len(hms) == 1:
    # assume seconds
    return int(hms[0])
  elif len(hms) == 2:
    # assume hh:mm
    return int(hms[0]) * 3600 + int(hms[1]) * 60
  elif len(hms) == 3:
    # assume hh:mm:ss
    return int(hms[0]) * 3600 + int(hms[1]) * 60 + int(hms[2])
  else:
    # unknown
    return 0


class Stream():
  def __init__(self, url):
    self.url = url
    self.started = False
    self.fully_cached = False
    self.chunk_len = 160*1024
    self.state_path = os.path.join(_dataDir_, sha1(url).hexdigest())
    _, ext = os.path.splitext(url)
    if not ext:
      ext = '.stream'
    self.cache_fn   = sha1(url).hexdigest() + ext
    self.cache_path = os.path.join(_tempDir_, self.cache_fn)
    print (_di_ + "url:   " + self.url)
    print (_di_ + "state: " + self.state_path)
    print (_di_ + "cache: " + self.cache_path)

    if os.path.exists(self.state_path):
      f = open(self.state_path)
      self.info = cPickle.loads(f.read())
      f.close()
      print (_di_+"Loading existing stream... (playback_pos=" + str(self.info['playback_pos']) + ")")
    else:
      self.info = {}
      print (_di_+"Loading new stream...")

    # Make sure all expected values are present.
    for k,v in {'url': self.url, 'playback_pos': 0.0, 'size': -1, 'playcount': 0}.iteritems():
      if k not in self.info:
        self.info[k] = v

  def restart(self):
    self.info['playback_pos'] = 0.0

  def resumable(self):
    return self.info['playback_pos'] > 0

  def isFullyCached(self):
    self.cache = open(self.cache_path, 'ab')
    pos = self.cache.tell()
    self.cache.close()

    return pos == self.info['size']

  def getDurationSecs(self):
    return time_str2secs(self.info['duration'])

  def openInstream(self, req):
    self.instream = urllib2.urlopen(req)

    length = int(self.instream.headers['Content-Length'])
    if not length:
      print (_di_+self.instream.headers)
    self.info['size'] = length
    print (_di_+"Updating file size: " + str(length))

  def open_cache(self):
    global last_cached

    if self.cache_fn not in last_cached:
      last_cached.append(self.cache_fn)

    while len(last_cached) > max_cached:
      last = last_cached[0]
      print(_di_+"Deleting cache " + last)
      try:
        os.unlink(os.path.join(_tempDir_, last))
      except OSError, e:
        print (_di_+"Failed to delete cache file: " + str(e))
        xbmc.executebuiltin("Notification("+_lang_(30200)+", "+_lang_(30201)+", 7000)")
      last_cached = last_cached[1:]

      fh = open(_lastCached_, 'wb')
      cPickle.dump(last_cached, fh)
      fh.close()

  def start(self):
    self.started = True
    self.open_cache ()
    self.cache = open(self.cache_path, 'ab')
    pos = self.cache.tell()

    req = urllib2.Request(self.url)

    if not self.info['size'] or self.info['size'] == -1:
      # size is unknown, update it
      self.openInstream(req)
      self.instream.close()

    if pos == self.info['size']:
      self.fully_cached = True
      print (_di_+"Caching already done.")
      return

    if pos == 0:
      print (_di_+"Requesting whole file")

      self.openInstream(req)

      print (_di_+"Initial request, total size is " + str(self.info['size']))

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

  def save(self):
    f = open(self.state_path, 'w')
    f.write(cPickle.dumps(self.info))
    f.close()

  def stop(self, playback_pos):
    if playback_pos:
      self.info['playback_pos'] = playback_pos
    if self.started:
      self.info['last_access'] = time.time()

    self.save()

    if self.started and not self.fully_cached:
      self.instream.close()
      self.cache.close()
    self.started = False

  def ended(self):
    self.info['playcount'] += 1
    self.stop(0)


class StreamPlayer(xbmc.Player):
  def __init__(self, *args):
    super(xbmc.Player, self).__init__(*args)

  def _prepare(self, stream):
    self._stream = stream
    self._resumed = False

  def onPlaybackEnded (self, *args):
    print (_di_ + "Playback ended, position = " + str(self.getTime()))
    self._stream.ended()
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
      self._stream.save()
    self._resumed = False


def main():
  print (_di_+" ARGS " + ", ".join (sys.argv))
  if sys.argv[0].startswith('plugin://' + _addon_id_):
    # called from the GUI
    params = url_query_to_dict(sys.argv[2])

    src = params.get('src')
    url = params.get('url')
    if url:
      url = urllib.url2pathname(url)
    play = False
  else:
    # called from RunScript(...) below
    url = sys.argv[1]
    play = True


  if url and play:
    # Play it.
    stream = Stream(url)

    player = StreamPlayer()

    player._prepare(stream)
    stream.start()

    li = xbmcgui.ListItem(stream.info['title'])
    li.setInfo('music', {'title':stream.info['title'],
                         'duration': stream.getDurationSecs(),
                         'playcount': stream.info['playcount'],
                         })
    player.play(stream.cache_path, li)

    # wait for xbmc to catch up and start
    while player._resumed == False:
      xbmc.sleep(200)

    while player.isPlayingAudio() and not xbmc.abortRequested:
      # Keep script alive so that we can save the state when playing stops.
      #print (_di_+"Still playing...")
      try:
        last_playback_pos = player.getTime()
      except:
        last_playback_pos = False

      stream.process()
      xbmc.sleep(1000)

    if stream.started:
      print (_di_ + "Unclean shutdown detected, last position is " + str(last_playback_pos))
      stream.stop(last_playback_pos)

    print (_di_ + "Bye!")

  elif url:
    print (_di_+"Asking what to do for " + url)
    stream = Stream(url)

    modes_lang = {
        'play'    : 30100,
        'resume'  : 30101,
        'restart' : 30102,
        'seek'    : 30103,
        'about'   : 30104,
        }
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

    dialog = xbmcgui.Dialog()
    mode = dialog.select(stream.info['title'], [_lang_(modes_lang[m]) for m in modes])
    print (_di_+"Selected " + str(mode))
    del dialog

    if mode != -1 and modes[mode] == 'about':
      dialog = xbmcgui.Dialog()
      dialog.ok(stream.info['title'], stream.info['description'], stream.info['duration'], stream.info['pubdate'])
      del dialog
    elif mode != -1: # all other modes are handled here
      print (_di_ + "Playing url %s" % url)
      if modes[mode] == 'restart':
        stream.restart()
      elif modes[mode] == 'seek':
        dialog = xbmcgui.Dialog()
        hours = int(stream.info['playback_pos'] / 3600)
        minutes = int((stream.info['playback_pos'] % 3600) / 60)
        seek_to = dialog.numeric(2, "Jump to", "%02d:%02d"%(hours ,minutes))
        if seek_to:
          print (_di_+ "Manually seeking to " + seek_to)
          stream.info['playback_pos'] = time_str2secs(seek_to)
        del dialog

      # save infos in case we selected restart or seek
      stream.save()

      u = "RunScript(" + _addon_id_ + ", " +  url + ")"
      print (_di_+"Launching playing instance for " + u)
      xbmc.executebuiltin(u)

      print (_di_+"See you on the other side.")


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
        if info[k] is not None:
          info[k] = info[k].text
        else:
          info[k] = '(not found)'

      url = f.find('enclosure').attrib['url']
      stream = Stream(url)
      stream.info.update(info)
      stream.save()

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
