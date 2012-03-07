#!/usr/bin/python

import socket, traceback, thread, time, sys
from datetime import datetime

def encode(d):
  assert isinstance(d, dict), "Data must be dict"
  return ";".join(("%s=%r" % (key, value) for (key, value) in d.iteritems()))
  
def decode(d):
  assert isinstance(d, basestring), "Data must be string"
  data = {}
  for entry in d.split(";"):
    (key, value) = entry.split("=")
    data[key] = eval(value)
  return data
  
def receiveLoop():
  while running:
    try:    
      (msg, src) = sock.recvfrom(1024)
      onReceive(src, decode(msg))
    except:
      if running:
        traceback.print_exc()

def onReceive(src, msg): #This is called when new messages are received
  n = msg["nickname"]
  if n == nickname: #ignore messages from us
    return
  time_received = time.time()
  delay = time_received - msg["time_sent"]
  expected_seqnum = seqNums.get(n, 0)+1
  seqNums[n] = msg["seqnum"]
  print "From %(nickname)s: %(msg)s" % msg
  print "  Delay: %.2f ms" % ( delay * 1000.0 )
  if msg["seqnum"] != expected_seqnum:
    print "  Sequence number mismatch detected: seqnum=%d, expected=%d" % (msg["seqnum"], expected_seqnum)
  
def send(msg): #Call this to send a message
  data = {"msg": msg, "nickname": nickname}
  data["time_sent"] = time.time()
  global seqNum
  seqNum += 1
  data["seqnum"] = seqNum
  sock.sendto(encode(data), address)

def sendLoop(msg, timeout):
  while running:
    time.sleep(timeout)
    send(msg)
    
def interactiveSendLoop():
  while running:
    msg = raw_input()
    if msg:
      send(msg)


#Read command-line parameters
try:
  broadcast = sys.argv[1] #Broadcast address
  port = int(sys.argv[2]) #Port is the first parameter
  address = (broadcast, port)
  nickname = sys.argv[3] #Nickname is second parameter
except:
  print "Usage: %s broadcast port nickname" % sys.argv[0]
  sys.exit(-1)

#Open socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
sock.settimeout(None)
sock.bind(address)

seqNum = 0
seqNums = {}

#Start receive loop in separate thread
running = True
thread.start_new_thread(receiveLoop, ())

send("[enter]") #send a message at begin
try:
  interactiveSendLoop()
except KeyboardInterrupt:
  pass
except:
  traceback.print_exc()
finally:
  running = False
  send("[exit]") #send a message at end