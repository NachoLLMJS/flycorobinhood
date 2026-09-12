"""Optional X/Twitter meeting publisher using OAuth 1.0a user context."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.parse
import urllib.request
import urllib.error


class XPublisher:
    endpoint = 'https://api.x.com/2/tweets'

    def __init__(self, env=None):
        env = env or os.environ
        prefix = 'FLYCOROBINHOOD_X_'
        self.enabled = env.get(prefix + 'POST_MEETINGS', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}
        self.consumer_key = env.get(prefix + 'CONSUMER_KEY', '').strip()
        self.consumer_secret = env.get(prefix + 'CONSUMER_SECRET', '').strip()
        self.bearer_token = env.get(prefix + 'BEARER_TOKEN', '').strip()
        self.access_token = env.get(prefix + 'ACCESS_TOKEN', '').strip()
        self.access_token_secret = env.get(prefix + 'ACCESS_TOKEN_SECRET', '').strip()

    def configured(self):
        return self.enabled and all((self.consumer_key, self.consumer_secret, self.access_token, self.access_token_secret))

    def reason(self):
        if not self.enabled:
            return 'X meeting posts are disabled'
        if not self.consumer_key or not self.consumer_secret:
            return 'X consumer credentials are missing'
        if not self.access_token or not self.access_token_secret:
            return 'X user access token credentials are missing; a bearer token cannot publish tweets'
        return ''

    @staticmethod
    def tweet_text(summary, meeting_id=None, recent_texts=()):
        normalized = ' '.join(str(summary or '').split())
        sentences = [part.strip() for part in re.split(r'(?<=[.!?])\s+', normalized) if part.strip()]
        candidates = []
        for selected in reversed(sentences):
            words = selected.split()
            if len(words) < 8 and len(sentences) > 1:
                words = (sentences[max(0, sentences.index(selected) - 1)] + ' ' + selected).split()
            candidates.append(' '.join(['FlyCo Robinhood meeting:'] + words[:26])[:280].rstrip())
        if not candidates:
            candidates = ['FlyCo Robinhood meeting:']
        previous = set(recent_texts or ())
        return next((text for text in candidates if text not in previous), candidates[0])

    @staticmethod
    def _quote(value):
        return urllib.parse.quote(str(value), safe='~-._')

    def _authorization(self, method, url):
        oauth = {
            'oauth_consumer_key': self.consumer_key,
            'oauth_nonce': secrets.token_hex(16),
            'oauth_signature_method': 'HMAC-SHA1',
            'oauth_timestamp': str(int(time.time())),
            'oauth_token': self.access_token,
            'oauth_version': '1.0',
        }
        parsed = urllib.parse.urlsplit(url)
        base_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))
        params = sorted((self._quote(k), self._quote(v)) for k, v in oauth.items())
        normalized = '&'.join(f'{k}={v}' for k, v in params)
        base = '&'.join((method.upper(), self._quote(base_url), self._quote(normalized)))
        key = self._quote(self.consumer_secret) + '&' + self._quote(self.access_token_secret)
        digest = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
        oauth['oauth_signature'] = base64.b64encode(digest).decode()
        return 'OAuth ' + ', '.join(f'{self._quote(k)}="{self._quote(v)}"' for k, v in sorted(oauth.items()))

    def post(self, summary, meeting_id=None, recent_texts=()):
        if not self.configured():
            return {'posted': False, 'reason': self.reason()}
        text = self.tweet_text(summary, meeting_id, recent_texts)
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps({'text': text}).encode('utf-8'),
            headers={'Authorization': self._authorization('POST', self.endpoint), 'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = json.loads(response.read(128001).decode('utf-8'))
            tweet_id = body.get('data', {}).get('id')
            return {'posted': bool(tweet_id), 'tweetId': tweet_id, 'text': text, 'reason': '' if tweet_id else 'X returned no tweet ID'}
        except urllib.error.HTTPError as exc:
            return {'posted': False, 'reason': f'X publish failed (HTTP {exc.code})'}
        except Exception as exc:
            return {'posted': False, 'reason': f'X publish failed ({type(exc).__name__})'}
