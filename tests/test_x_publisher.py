import unittest
import io
import json
from unittest.mock import patch

from x_publisher import XPublisher


class XPublisherTests(unittest.TestCase):
    @staticmethod
    def configured_env():
        return {
            'FLYCOROBINHOOD_X_POST_MEETINGS': 'true',
            'FLYCOROBINHOOD_X_CONSUMER_KEY': 'consumer',
            'FLYCOROBINHOOD_X_CONSUMER_SECRET': 'secret',
            'FLYCOROBINHOOD_X_ACCESS_TOKEN': 'token',
            'FLYCOROBINHOOD_X_ACCESS_TOKEN_SECRET': 'token-secret',
            'FLYCOROBINHOOD_X_EXPECTED_USERNAME': 'flycorobinhood',
            'FLYCOROBINHOOD_PUBLIC_X_PROFILE_URL': 'https://x.com/flycorobinhood',
        }

    def test_tweet_text_is_at_most_30_words_and_280_chars(self):
        text = XPublisher.tweet_text(' '.join(f'word{i}' for i in range(100)), 'meeting-123')
        self.assertLessEqual(len(text.split()), 30)
        self.assertLessEqual(len(text), 280)

    def test_meeting_hint_prevents_identical_posts(self):
        summary = 'A repeated meeting decision with the same opening text. A new research task follows.'
        first = XPublisher.tweet_text(summary, 'first-meeting')
        second = XPublisher.tweet_text(summary, 'second-meeting', [first])
        self.assertNotEqual(first, second)
        self.assertNotIn('first-meeting', first)
        self.assertNotIn('second-meeting', second)
        self.assertLessEqual(len(first.split()), 30)
        self.assertLessEqual(len(second.split()), 30)

    def test_tweet_uses_the_conclusion_instead_of_repeated_opening(self):
        summary = 'The recurring opening says no launch. New evidence requires a different research test before any decision.'
        text = XPublisher.tweet_text(summary, 'meeting-123')
        self.assertIn('New evidence requires', text)
        self.assertNotIn('The recurring opening says', text)
        self.assertLessEqual(len(text.split()), 30)

    def test_bearer_token_alone_cannot_publish(self):
        publisher = XPublisher({
            'FLYCOROBINHOOD_X_POST_MEETINGS': 'true',
            'FLYCOROBINHOOD_X_CONSUMER_KEY': 'consumer',
            'FLYCOROBINHOOD_X_CONSUMER_SECRET': 'secret',
            'FLYCOROBINHOOD_X_BEARER_TOKEN': 'bearer',
        })
        self.assertFalse(publisher.configured())
        self.assertIn('user access token', publisher.reason())
        self.assertFalse(publisher.post('A meeting summary')['posted'])

    def test_posting_can_be_disabled(self):
        publisher = XPublisher({'FLYCOROBINHOOD_X_POST_MEETINGS': 'false'})
        self.assertFalse(publisher.configured())
        self.assertIn('disabled', publisher.reason())

    def test_generic_x_credentials_from_another_project_are_ignored(self):
        publisher = XPublisher({
            'X_POST_MEETINGS': 'true',
            'X_CONSUMER_KEY': 'old-consumer',
            'X_CONSUMER_SECRET': 'old-secret',
            'X_ACCESS_TOKEN': 'old-token',
            'X_ACCESS_TOKEN_SECRET': 'old-token-secret',
        })
        self.assertFalse(publisher.enabled)
        self.assertFalse(publisher.configured())
        self.assertEqual('', publisher.consumer_key)

    def test_configuration_requires_expected_username_and_matching_public_profile(self):
        env = self.configured_env()
        env.pop('FLYCOROBINHOOD_X_EXPECTED_USERNAME')
        publisher = XPublisher(env)
        self.assertFalse(publisher.configured())
        self.assertIn('expected username', publisher.reason().lower())

        env = self.configured_env()
        env['FLYCOROBINHOOD_PUBLIC_X_PROFILE_URL'] = 'https://x.com/a-different-account'
        publisher = XPublisher(env)
        self.assertFalse(publisher.configured())
        self.assertIn('does not match', publisher.reason().lower())

    def test_post_verifies_authenticated_username_before_publishing(self):
        publisher = XPublisher(self.configured_env())
        responses = [
            io.BytesIO(json.dumps({'data': {'username': 'different-account'}}).encode()),
        ]
        with patch('x_publisher.urllib.request.urlopen', side_effect=responses) as request:
            result = publisher.post('Safe summary for the configured account.')
        self.assertFalse(result['posted'])
        self.assertIn('identity mismatch', result['reason'].lower())
        self.assertEqual(request.call_count, 1)

    def test_post_publishes_only_after_authenticated_username_matches(self):
        publisher = XPublisher(self.configured_env())
        responses = [
            io.BytesIO(json.dumps({'data': {'username': 'FlyCoRobinhood'}}).encode()),
            io.BytesIO(json.dumps({'data': {'id': 'tweet-1'}}).encode()),
        ]
        with patch('x_publisher.urllib.request.urlopen', side_effect=responses) as request:
            result = publisher.post('Safe summary for the configured account.')
        self.assertTrue(result['posted'])
        self.assertEqual(result['tweetId'], 'tweet-1')
        self.assertEqual(request.call_count, 2)


if __name__ == '__main__':
    unittest.main()
