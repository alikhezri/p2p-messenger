class ReceiveMessageException(Exception):
    """Raised when could not receive message successfully"""

    def __str__(self) -> str:
        return super().__str__()


class ReceiveTCPMessageException(ReceiveMessageException):
    """Raised when could not receive TCP message successfully"""

    def __str__(self) -> str:
        return super().__str__()


class ReceiveUDPMessageException(ReceiveMessageException):
    """Raised when could not receive UDP message successfully"""

    def __str__(self) -> str:
        return super().__str__()


class HandshakeException(Exception):
    """Raised when could not handshake successfully"""

    def __str__(self) -> str:
        return super().__str__()


class TransceiveHandshakeKeyException(HandshakeException):
    """Raised when could transceive handshake ack successfully"""

    def __str__(self) -> str:
        return super().__str__()


class TransceiveHandshakeAckException(HandshakeException):
    """Raised when could transceive handshake key successfully"""

    def __str__(self) -> str:
        return super().__str__()
