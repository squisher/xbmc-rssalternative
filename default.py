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
import threading

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
rewind_secs = int(_settings_.getSetting('rewindSecs'))

def url_query_to_dict(url):
  ''' Returns the URL query args parsed into a dictionary '''
  param = {}
  if url:
    u = urlparse.urlparse(url)
    for q in u.query.split('&'):
      kvp = q.split('=')
      param[kvp[0]] = urllib.url2pathname(kvp[1])

  return param

def time_str2secs(s):
  hms = s.split(':')
  if len(hms) == 1:
    # assume seconds
    return int(hms[0])
  elif len(hms) == 2:
    # assume mm:ss
    return int(hms[0]) * 60 + int(hms[1])
  elif len(hms) == 3:
    # assume hh:mm:ss
    return int(hms[0]) * 3600 + int(hms[1]) * 60 + int(hms[2])
  else:
    # unknown
    print (_di_+"Unable to parse time string "+ s)
    return 0

def time_secs2str(tm):
    s = int(tm % 60)
    tm /= 60
    m = int(tm % 60)
    h = int(tm / 60)

    return "{0:d}:{1:02d}:{2:02d}".format(h,m,s)

def urlopen(req, abort=True):
  try:
    return urllib2.urlopen(req)
  except rangereq.RangeError, e:
    print(_di_+url+": "+str(e))
    xbmc.executebuiltin("Notification("+_lang_(30202)+", "+_lang_(30201)+", 7000)")
    if abort:
      sys.exit(1)
  except urllib2.URLError, e:
    print(_di_+url+": "+str(e))
    xbmc.executebuiltin("Notification("+_lang_(30203)+", "+url+"\n"+str(e)+", 7000)")
    if abort:
      sys.exit(1)


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

    self.mutex = threading.Semaphore()

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

    return pos >= self.info['size']

  def getDurationSecs(self):
    return time_str2secs(self.info['duration'])

  def openInstream(self, req):
    self.instream = urlopen(req)

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
    self.mutex.acquire()

    self.started = True
    self.open_cache ()
    self.cache = open(self.cache_path, 'ab')
    pos = self.cache.tell()

    req = urllib2.Request(self.url)

    if not self.info['size'] or self.info['size'] == -1:
      # size is unknown, update it
      self.openInstream(req)
      self.instream.close()

    if pos >= self.info['size']:
      if pos > self.info['size']:
        print (_di_+"Warning:", self.cache_path, "is bigger than the expected size (is:", pos, ", should be: ", self.info['size'], ")")
      else:
        print (_di_+"Caching already done.")

      self.fully_cached = True
      self.mutex.release()
      return

    # initial_size needs to be bigger than xbmc's buffer, otherwise playback will be
    # interrupted
    initial_size = 3*1024*1024
    if initial_size > self.info['size']:
      initial_size = self.info['size']

    if pos < initial_size:
      if pos > 0:
        req.headers['Range'] = 'bytes=' + str(pos) + '-'
        print (_di_+"Requesting range " + req.headers['Range'])
      else:
        print (_di_+"Requesting whole file")

      self.openInstream(req)

      print (_di_+"Initial buffering")

      step_size = initial_size / 20
      read_size = 0

      win = xbmcgui.DialogProgress()
      ret = win.create('Caching', self.info['description'])
      win.update(1)

      while read_size < initial_size and not win.iscanceled():
        data = self.instream.read(step_size)
        self.cache.write(data)
        read_size += len(data)
        print (_di_+"Updating GUI to "+ str(int(read_size * 100.0 / initial_size))+ " after caching " + str(len(data)))
        win.update(int(read_size * 100.0 / initial_size))
        xbmc.sleep(10)

      win.close()

      if win.iscanceled():
        print(_di_+"Cancelled, aborting.")
        sys.exit(1)

    else:
      req.headers['Range'] = 'bytes=' + str(pos) + '-'
      print (_di_+"Requesting range " + req.headers['Range'])

      self.instream = urlopen(req)

      data = self.instream.read(self.chunk_len)

    #print (_di_+"Caching " + str(len(data)) + " bytes")
    self.cache.write(data)

    self.mutex.release()

  def process(self):
    if self.fully_cached:
      xbmc.sleep(1000)
      return

    self.mutex.acquire()

    if self.started == False:
      self.mutex.release()
      return

    data = self.instream.read(self.chunk_len)
    #print (_di_+"Caching " + str(len(data)) + " bytes")
    self.cache.write(data)
    if data < self.chunk_len:
      print (_di_+"Caching is done!")
      self.fully_cached = True
      self.instream.close()
      self.cache.close()

    self.mutex.release()

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

    self.mutex.acquire()

    if self.started and not self.fully_cached:
      self.instream.close()
      self.cache.close()
    self.started = False

    self.mutex.release()

  def ended(self):
    self.info['playcount'] += 1
    self.stop(0)

  def shutdown(self, last_playback_pos):
    """
    Just a safety net, in case the OnPlayback{Stopped,Ended} method didn't get called.
    """
    self.mutex.acquire()

    if self.started:
      print (_di_ + "Unclean shutdown detected, last position is " + str(last_playback_pos))
      self.stop(last_playback_pos)

    self.mutex.release()


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


def play_string(k, stream):
    modes_lang = {
        'play'    : 30100,
        'resume'  : 30101,
        'restart' : 30102,
        'seek'    : 30103,
        'about'   : 30104,
        }
    s = _lang_(modes_lang[k])
    if k == 'play':
        s += ' (' + stream.info['duration'] + ')'
    elif k == 'resume':
        s += ' (' + time_secs2str(stream.info['playback_pos']) + ' / ' + stream.info['duration'] + ')'
    return s


#def parse_time(tstr):
#  """Parse strings in the `Last-Modified' format:
#    Sat, 12 Oct 2013 18:19:41 GMT
#  into a unix timestamp
#  """
#  import datetime
#  fmt = '%a, %d %b %Y %H:%M:%S %Z'
#  try:
#    dt = datetime.datetime.strptime(tstr, fmt)
#    return dt.strftime("%s")
#  except TypeError:
#    tm = time.strptime(tstr, fmt)
#    return time.strftime("%s", tm)


class RSS(object):
  def __init__(self, url):
    self.url = url
    _, ext = os.path.splitext(url)
    if not ext:
      ext = '.rss'
    self.cache_fn   = sha1(url).hexdigest() + ext
    self.cache_path = os.path.join(_tempDir_, self.cache_fn)

    self.load()

  def load(self):
    if os.path.exists(self.cache_path):
      f = open(self.cache_path)
      self.info = cPickle.loads(f.read())
      f.close()
    else:
      self.info = {'last_mod': '', 'items': [], 'thumbnail': ''}

  def save(self):
    print(_di_+"Saving feed cache")
    fh = open(self.cache_path, 'wb')
    cPickle.dump(self.info, fh)
    fh.close()

  def parse(self, fh):
    tree = ElementTree()
    root = tree.parse(fh)

    channel = root.find('./channel')
    img = channel.find('./itunes:image', namespaces=dict(itunes='http://www.itunes.com/dtds/podcast-1.0.dtd'))

    if img is not None and 'href' in img.attrib:
      self.info['thumbnail'] = img.attrib['href']

    entries = channel.findall('./item')

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

      info['url'] = f.find('enclosure').attrib['url']
      self.info['items'].append(info)

  def getItems(self):
    req = urllib2.Request(self.url)
    self.instream = urlopen(req)
    feed_mod = self.instream.headers['Last-Modified']
    if feed_mod != self.info['last_mod']:
      self.info['last_mod'] = feed_mod
      print (_di_+"Fetching feed")
      self.parse(self.instream)
      self.save()
    else:
      print (_di_+"Using cache of feed from "+feed_mod)
    self.instream.close()

    return self.info['items']

  def thumbnail(self):
    return self.info['thumbnail']



def main():
  print (_di_+" ARGS " + ", ".join (sys.argv))
  if sys.argv[0].startswith('plugin://' + _addon_id_):
    # called from the GUI
    params = url_query_to_dict(sys.argv[2])

    src = params.get('src')
    url = params.get('url')
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
      xbmc.sleep(100)

    stream.shutdown(last_playback_pos)

    print (_di_ + "Bye!")

  elif url:
    print (_di_+"Asking what to do for " + url)
    stream = Stream(url)

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
    mode = dialog.select(stream.info['title'], [play_string(m, stream) for m in modes])
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
      elif modes[mode] == 'resume':
        stream.info['playback_pos'] -= rewind_secs


      # save info in case we selected restart or seek
      stream.save()

      u = "RunScript(" + _addon_id_ + ", " +  url + ")"
      print (_di_+"Launching playing instance for " + u)
      xbmc.executebuiltin(u)

      print (_di_+"See you on the other side.")


  elif src:
    print (_di_ + "Showing entries for " + src)

    rss = RSS(sources[src])

    for info in rss.getItems():
      url = info['url']

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
      rss = RSS(sources[k])

      u = sys.argv[0] + '?' + urllib.urlencode({'src': k})
      li = xbmcgui.ListItem(k, thumbnailImage=rss.thumbnail())
      xbmcplugin.addDirectoryItem(handle = int(sys.argv[1]),
                                  url = u, listitem = li,
                                  isFolder = True)
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


main()
# vim:tabstop=8 expandtab shiftwidth=2 softtabstop=2
