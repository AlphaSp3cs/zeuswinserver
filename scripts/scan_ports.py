import socket
ports=[8080,9000,5000,5001]
for p in ports:
 s=socket.socket(); s.settimeout(2)
 try:
  s.connect(('10.0.188.50',p)); print('OPEN',p)
  try: print(s.recv(4096).decode('utf-8','replace').strip())
  except: pass
 except Exception as e: print('CLOSED',p,str(e))
 finally: s.close()
