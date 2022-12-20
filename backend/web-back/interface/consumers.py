import asyncio
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from os import environ
from tweepy import TweepyException, StreamRule
from .models import StreamRules, Tweet, Event
from .livetweets import LiveStream, EngagementTracker, set_rules_to_inactive
from django.core.cache import caches

TWITTER_BEARER_TOKEN = environ['TWITTER_BEARER_TOKEN']

STREAM = None

""" Helper functions for sync_to_async """
def get_dupe_rule_ids(tag):
    """
    Takes in a rule tag and returns the ids of rules with this tag
    :param tag: The tag attribute of a rule
    :return: The ids of rules with the provided tag
    """
    dupes = StreamRules.objects.filter(tag=tag)
    ids = [item[0] for item in dupes.values_list('id')]
    return ids


def get_tweet_time(tweetid):
    """
    Takes a tweetid and returns the time the tweet was created
    :param tweetid: A tweetid as a string
    :return: The 'created_at' attribute of the tweet
    """
    tweet = Tweet.objects.get(pk=tweetid)
    time = tweet.created_at
    return time


""" The consumer class for our Websocket"""
class TweetConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        """
        In addition to the inbuilt functions, we are also giving the consumers variables we need for some of
        the operations we want to perform.
        STREAM is for storing the instatiated streaming object
        session is for storing the session of which the stream was instantiated (not implemented)
        :param args:
        :param kwargs:
        """
        super().__init__(*args, **kwargs)
        self.STREAM = STREAM
        self.session = None
        self.engagement_tracker = EngagementTracker(TWITTER_BEARER_TOKEN)

    async def connect(self):
        """
        Currently only connects to the 'tweet' group. For multiple concurrent connections, the consumer
        should receive a group through the URL request, and connect to that instead.
        Accept any incoming connection.
        """
        await self.channel_layer.group_add('tweet', self.channel_name)
        await self.accept()

        try:
            matches = Event.objects.filter(tracked=True)
        except Event.DoesNotExist:
            print("No tracked matches")

        matches_list = []

        async for match in matches:
            matchobj = {
                'id': match.id,
                'name': match.name
            }
            matches_list.append(matchobj)


        await self.send(text_data=json.dumps({
            'type': 'matchlist',
            'matches': matches_list}))

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

        if self.STREAM.filtering is False:
            try:
                res = self.STREAM.filter(
                    tweet_fields=['id', 'text', 'attachments', 'author_id', 'context_annotations', 'conversation_id',
                                  'created_at', 'entities', 'geo', 'in_reply_to_user_id', 'lang', 'possibly_sensitive',
                                  'public_metrics', 'reply_settings', 'source', 'withheld'],
                    expansions=['entities.mentions.username', 'geo.place_id', 'author_id', 'attachments.media_keys'],
                    place_fields=['contained_within', 'country', 'country_code', 'full_name', 'name', 'place_type'],
                    media_fields=['url', 'preview_image_url'])
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'stream': 'Stream connecting'}))
            except TweepyException:
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'stream': f'{TweepyException}'}))




    async def receive(self, text_data=None, bytes_data=None):
        """
        Catch incoming messages from the websocket and perform the associated task.
        The tasks are referred to in the 'task' attribute.
        We are currently handling the following tasks:

        'loadstream': Initiates the LiveStream instance runs the class' 'update_rules_from_twitter' method,
        and sends the message "Stream initiated" back to the websocket.

        'startstream': Establishes the connection to twitter, and starts receiving tweets.

        'stopstream': Stops the streaming connection to twitter. Also stops the engagement tracking loop.

        'rulelist': Reads the 'rules' attribute of the message, checks the database for duplicate rules, deletes any
        duplicate rules from twitter, and finally adds the new rules to the stream.

        'deleterules': Deletes any rules from twitter, and sets them to "inactive" in the database.

        :param text_data: The text_data from the websocket
        :param bytes_data: The bytes_data from the websocket
        :return:
        """
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
                                  'public_metrics', 'reply_settings', 'source', 'withheld'],
                    expansions=['entities.mentions.username', 'geo.place_id', 'author_id', 'attachments.media_keys'],
                    place_fields=['contained_within', 'country', 'country_code', 'full_name', 'name', 'place_type'],
                    media_fields=['url', 'preview_image_url'])
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
        """
        Recieved upon a connection dropping from the websocket.
        In that case we stop the engagement tracking, disconnect the stream, and unsubscribe from the 'tweet'
        channel.
        :param code: The disconnection code received from the websocket
        """
        # self.engagement_tracker.tracking = False
        # if self.STREAM is not None:
        #     self.STREAM.disconnect()
        # await self.channel_layer.group_discard('tweet', self.channel_name)

    async def tweet(self, event):
        """
        Upon receiving a tweet over the group_channel sends the tweet ID, the matching filter(s)
        to the consumers, and starts the engagement tracking if its not already running.

        TODO: Expand this, along with the associated part of the LiveStream on_response method to send the tweet
        TODO: data needed to draw the tweet, as well as the created_at parameter for the engagement_update function

        :param event: The message received over the group channel.
        """
        print('Tweet: ', event)

        # await self.send(text_data=json.dumps({
        #     'type': event['type'],
        #     'id': event['id'],
        #     'filters': event['filters']
        # }))
        if not self.engagement_tracker.tracking:
            self.engagement_tracker.tracking = True
            a = asyncio.get_event_loop()

            events_found = False
            try:
                events = Event.objects.filter(tracked=True)
                events_found = True

            except Event.DoesNotExist:
                events_found = False
                print("No Tracked Events")

            if events_found:
                async for event in events:
                    e = await event
                    a.create_task(self.engagement_tracker.periodic_update(30, self.engagement_tracker.engagement_update,
                                                                          match=e))
                # match = await Event.objects.aget(name='Argentina vs France')
                # a.create_task(self.engagement_tracker.periodic_update(30, self.engagement_tracker.engagement_update,
                #                                                       match=match))
                # match = await Event.objects.aget(name='Croatia vs Morocco')
                # a.create_task(self.engagement_tracker.periodic_update(30, self.engagement_tracker.engagement_update,
                #                                                   match=match))

    async def status(self, event):
        """
        When receiving a status message, forward it over the websocket
        :param event: The message received over the group channel.
        """
        print('Status: ', event)
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'stream': event['message']
        }))

    async def rule(self, event):
        """
        When receiving a rule over the group channel, forward it over the websocket
        :param event: The message received over the group channel.
        """
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'id': event['id'],
            'filter': event['filters'],
            'tag': event['tag']
        }))

    async def hmc(self, event):
        """
        When receiving hashtags, mentions and contexts, forward them over the websocket.
        :param event: The message received over the group channel.
        """
        # await self.send(text_data=json.dumps({
        #     'type': event['type'],
        #     'hashtags': event['hashtags'],
        #     'mentions': event['mentions'],
        #     'contexts': event['contexts']
        # }))

    async def tweetmetrics(self, event):
        """
        When receiving tweet metrics, forward them over the websocket.
        :param event: The message received over the group channel.
        """
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'results': event['results'],
            'match': event['match']
        }))

