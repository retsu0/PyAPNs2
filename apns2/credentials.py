import time

import jwt

from hyper import HTTP20Connection  # type: ignore
from hyper.tls import init_context  # type: ignore

DEFAULT_TOKEN_LIFETIME = 3600
DEFAULT_TOKEN_ENCRYPTION_ALGORITHM = 'ES256'


# Abstract Base class. This should not be instantiated directly.
class Credentials(object):
    def __init__(self, ssl_context=None):
        self.__ssl_context = ssl_context

    # Creates a connection with the credentials, if available or necessary.
    def create_connection(self, server, port, proto, proxy_host=None, proxy_port=None):
        # self.__ssl_context may be none, and that's fine.
        return HTTP20Connection(server, port, ssl_context=self.__ssl_context, force_proto=proto or 'h2',
                                secure=True, proxy_host=proxy_host, proxy_port=proxy_port)

    def get_authorization_header(self, topic):
        return None


# Credentials subclass for certificate authentication
class CertificateCredentials(Credentials):
    def __init__(self, cert_file=None, password=None, cert_chain=None):
        ssl_context = init_context(cert=cert_file, cert_password=password)
        if cert_chain:
            ssl_context.load_cert_chain(cert_chain)
        super(CertificateCredentials, self).__init__(ssl_context)


# Credentials subclass for JWT token based authentication
class TokenCredentials(Credentials):
    def __init__(self, auth_key_path, auth_key_id, team_id,
                 encryption_algorithm=DEFAULT_TOKEN_ENCRYPTION_ALGORITHM,
                 token_lifetime=DEFAULT_TOKEN_LIFETIME):
        self.__auth_key = self._get_signing_key(auth_key_path)
        self.__auth_key_id = auth_key_id
        self.__team_id = team_id
        self.__encryption_algorithm = encryption_algorithm
        self.__token_lifetime = token_lifetime

        # Dictionary of {topic: (issue time, ascii decoded token)}
        self.__jwt_token = None

        # Use the default constructor because we don't have an SSL context
        super(TokenCredentials, self).__init__()

    def get_authorization_header(self, topic):
        token = self._get_or_create_topic_token(topic)
        return 'bearer %s' % token

    @staticmethod
    def _is_expired_token(issue_date):
        return time.time() > issue_date + DEFAULT_TOKEN_LIFETIME

    @staticmethod
    def _get_signing_key(key_path):
        secret = ''
        if key_path:
            with open(key_path) as f:
                secret = f.read()
        return secret

    def _get_or_create_topic_token(self, topic):
        # dict of topic to issue date and JWT token
        token_pair = self.__jwt_token
        if token_pair is None or self._is_expired_token(token_pair[0]):
            # Create a new token
            issued_at = time.time()
            token_dict = {
                'iss': self.__team_id,
                'iat': issued_at,
            }
            headers = {
                'alg': self.__encryption_algorithm,
                'kid': self.__auth_key_id,
            }
            jwt_token = jwt.encode(token_dict, self.__auth_key,
                                   algorithm=self.__encryption_algorithm,
                                   headers=headers).decode('ascii')

            # Cache JWT token for later use. One JWT token per connection.
            # https://developer.apple.com/documentation/usernotifications/setting_up_a_remote_notification_server/establishing_a_token-based_connection_to_apns
            self.__jwt_token = (issued_at, jwt_token)
            return jwt_token
        else:
            return token_pair[1]
