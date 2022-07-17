import asyncio
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from os import environ
from tweepy import TweepyException, StreamRule

from .models import StreamRules, Tweet
from .livetweets import LiveStream, EngagementTracker, set_rules_to_inactive


TWITTER_BEARER_TOKEN = environ['TWITTER_BEARER_TOKEN']


# Helper functions for sync_to_async
def get_dupe_rule_ids(tag):
    dupes = StreamRules.objects.filter(tag=tag)
    ids = [item[0] for item in dupes.values_list('id')]
    return ids


def get_tweet_time(tweetid):
    tweet = Tweet.objects.get(pk=tweetid)
    time = tweet.created_at
    return time


class TweetConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.STREAM = None
        self.session = None
        self.engagement_tracker = EngagementTracker(TWITTER_BEARER_TOKEN)

    async def connect(self):
        await self.channel_layer.group_add('tweet', self.channel_name)
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        print('Receive: ', text_data)
        data = json.loads(text_data)
        if data['type'] == 'loadstream':
            if self.STREAM is not None:
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'stream': 'Stream already initiated'}))
                return
            self.STREAM = LiveStream(bearer_token=TWITTER_BEARER_TOKEN)
            await self.STREAM.update_rules_from_twitter()
            await self.send(text_data=json.dumps({
                'type': 'status',
                'stream': 'Stream initiated'}))
        if data['type'] == 'startstream':
            if self.STREAM is None:
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'stream': 'No active stream'}))
                return
            try:
                res = self.STREAM.filter(
                    tweet_fields=['id', 'text', 'attachments', 'author_id', 'context_annotations', 'conversation_id',
                                  'created_at', 'entities', 'geo', 'in_reply_to_user_id', 'lang', 'possibly_sensitive',
                                  'public_metrics', 'referenced_tweets', 'reply_settings', 'source', 'withheld'],
                    expansions=['entities.mentions.username', 'geo.place_id', 'author_id', 'attachments.media_keys'],
                    place_fields=['contained_within', 'country', 'country_code', 'full_name', 'name', 'place_type'],
                    media_fields=['url', 'preview_image_url'])
                print(res)
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'stream': 'Stream connecting'}))
            except TweepyException:
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'stream': f'{TweepyException}'}))

        if data['type'] == 'stopstream':
            if self.STREAM is None:
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'stream': 'No active stream'}))
                return
            self.STREAM.disconnect()
            await self.send(
                text_data=json.dumps({'type': 'status', 'stream': 'Disconnect signal sent'}))
            self.engagement_tracker.tracking = False

        if data['type'] == 'rulelist':
            if self.STREAM is None:
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'stream': 'No active stream'}))
                return
            rulelist = list()
            dupes = list()

            for rule in data['rules']:
                if rule['value']:
                    r = StreamRule(
                        value=rule['value'],
                        tag=rule['tag'],
                    )
                    ids = await sync_to_async(get_dupe_rule_ids)(rule['tag'])
                    for id in ids:
                        dupes.append(id)
                    rulelist.append(r)
            if dupes:
                await self.STREAM.delete_rules(dupes)
            await self.STREAM.add_rules(rulelist)
            await self.STREAM.update_rules_from_twitter()

        if data['type'] == 'deleterules':
            if self.STREAM is None:
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'stream': 'No active stream'}))
                return
            ids = list()
            rules = await self.STREAM.get_rules()
            if rules[0] is not None:
                for rule in rules[0]:
                    ids.append(rule.id)
                await self.STREAM.delete_rules(ids)
                rules = await self.STREAM.get_rules()
            if rules.data is None:
                await self.send(text_data=json.dumps({
                    'type': 'rulestatus',
                    'stream': 'No rules stored in stream'}))
                await sync_to_async(set_rules_to_inactive)()

    async def disconnect(self, code):
        self.engagement_tracker.tracking = False
        if self.STREAM is not None:
            self.STREAM.disconnect()
        await self.channel_layer.group_discard('tweet', self.channel_name)

    async def tweet(self, event):
        print('Tweet: ', event)
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'id': event['id'],
            'filters': event['filters']
        }))
        if not self.engagement_tracker.tracking:
            self.engagement_tracker.tracking = True
            a = asyncio.get_event_loop()
            starttime = await sync_to_async(get_tweet_time)(event['id'])
            a.create_task(self.engagement_tracker.periodic_update(30, self.engagement_tracker.engagement_update,
                                                                  starttime=starttime))

    async def status(self, event):
        print('Status: ', event)
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'stream': event['message']
        }))

    async def rule(self, event):
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'id': event['id'],
            'filter': event['filters'],
            'tag': event['tag']
        }))

    async def hmc(self, event):
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'hashtags': event['hashtags'],
            'mentions': event['mentions'],
            'contexts': event['contexts']
        }))

    async def tweetmetrics(self, event):
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'results': event['results']
        }))

