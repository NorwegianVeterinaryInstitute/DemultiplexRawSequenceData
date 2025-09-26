#!/usr/bin/python3.11

import logging
import socket


########################################################################
# BufferingSMTPHandler
########################################################################

class BufferingSMTPHandler( logging.handlers.BufferingHandler ):
    """
    Instead of immediatelly sending email for notifications, buffer the ouput and send it at the end.
    That way, you send one email instead of a multitude.
    """
    def __init__( self, mailhost, fromaddr, toaddrs, subject ):
        logging.handlers.BufferingHandler.__init__( self, capacity = 9999999 )
        self.mailhost = mailhost
        self.mailport = None
        self.fromaddr = fromaddr
        self.toaddrs = toaddrs
        self.subject = subject
        self.setFormatter( logging.Formatter( "%(asctime)s %(dns)s %(filename)s %(levelname)s %(message)s", datefmt = '%Y-%m-%d %H:%M:%S', defaults = { "dns": socket.gethostname( ) } ) )

    def flush(self):
        if len(self.buffer) > 0:
            import smtplib
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP( self.mailhost, port )
            msg = f"From: {self.fromaddr}\r\nTo: {self.toaddrs}\r\nSubject: {self.subject}\r\n\r\n"
            for record in self.buffer:
                s = self.format( record )
                print( s )
                msg = msg + s + '\r\n'
            msg = msg + '\r\n\r\n'
            smtp.sendmail( self.fromaddr, self.toaddrs, msg )
            smtp.quit( )
            self.buffer = []

