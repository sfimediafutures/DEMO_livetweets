import asyncio

from tweepy.asynchronous import AsyncClient, AsyncStreamingClient
from .models import *
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.utils import timezone
from collections import defaultdict

from datetime import datetime, timedelta


# Helper functions for Django ORM - to be fed into sync_to_async in async loops
def set_rules_to_inactive():
    StreamRules.objects.filter(active=True).update(active=False)


def add_tweet_to_db(tweet):
    tw = Tweet.objects.create(
                id=str(tweet.id),
                text=tweet.text,
                author_id=str(tweet.author_id),
                conversation_id=str(tweet.conversation_id),
                created_at=tweet.created_at,
                in_reply_to_user_id=str(tweet.in_reply_to_user_id),
                lang=tweet.lang,
                possibly_sensitive=tweet.possibly_sensitive,
                reply_settings=tweet.reply_settings,
                source=tweet.source
            )
    TrackedTweet.objects.create(
        tweetid=tw,
        created_at=tweet.created_at,
        metrics_per_update=0
    )
    if tweet['entities']:
        if 'hashtags' in tweet['entities']:
            for hashtag in tweet['entities']['hashtags']:
                tag = hashtag['tag']
                h = None
                try:
                    h = Hashtag.objects.get(hashtag=tag)
                    h.count += 1
                    h.save()
                except Hashtag.DoesNotExist:
                    h = Hashtag.objects.create(
                        hashtag=tag,
                        count=1
                    )
                except Hashtag.MultipleObjectsReturned:
                    print('Multiple hashtags found')
                tw.hashtags.add(h)

        if 'mentions' in tweet['entities']:
            for mention in tweet['entities']['mentions']:
                name = mention['username']
                m = None
                try:
                    m = Mention.objects.get(mention=name)
                    m.count += 1
                    m.save()
                except Mention.DoesNotExist:
                    m = Mention.objects.create(
                        mention=name,
                        count=1
                    )
                except Mention.MultipleObjectsReturned:
                    print('Multiple mentions found')
                tw.mentions.add(m)

    if 'context_annotations' in tweet:
        for context in tweet['context_annotations']:
            d = None
            try:
                d = ContextDomain.objects.get(dom_id=context['domain']['id'])
            except ContextDomain.DoesNotExist:
                d = ContextDomain(
                        dom_id=context['domain']['id'],
                        name=context['domain']['name']
                    )
                d.save()
            except ContextDomain.MultipleObjectsReturned:
                print('Multiple Domains returned')
            try:
                e = ContextEntity.objects.get(ent_id=context['entity']['id'])
                e.count += 1
                e.save()
            except ContextEntity.DoesNotExist:
                e = ContextEntity(
                    name=context['entity']['name'],
                    ent_id=context['entity']['id'],
                    domain=d,
                    count=1
                    )
                e.save()
            tw.context.add(e)


def update_metrics(tweetid, timestamp, retweet_count, reply_count, like_count, quote_count):
    TweetMetrics.objects.create(
        tweetid=Tweet.objects.get(id=tweetid),
        time=timestamp,
        retweet_count=retweet_count,
        reply_count=reply_count,
        like_count=like_count,
        quote_count=quote_count
    )


def get_tracked_tweets(starttime):
    tweets = TrackedTweet.objects.filter(created_at__gte=starttime).order_by("-created_at")[:99]
    ids = list(tweets.values_list('tweetid', flat=True))
    return ids


def get_10_popular_h_m_c():
    hashtags = list(Hashtag.objects.order_by("-count").values('hashtag', 'count'))
    mentions = Mention.objects.order_by("-count").values('mention', 'count')
    rules = StreamRules.objects.filter(active=True)
    ruletext = ''
    for rule in rules.values('value'):
        ruletext += ' ' + rule['value']
    htracked = [part[1:] for part in ruletext.replace('(', '').replace(')', '').split() if part.startswith('#')]
    mtracked = [part[1:] for part in ruletext.replace('(', '').replace(')', '').split() if part.startswith('@')]
    ctracked = [part[8:] for part in ruletext.replace('(', '').replace(')', '').split() if part.startswith('context:')]
    htags = [tag for tag in hashtags if tag['hashtag'] not in htracked]
    mnames = [name for name in mentions if name['mention'] not in mtracked]
    cents = ContextEntity.objects.order_by("-count")
    contexts = []
    for context in cents:
        c = dict()
        c['name'] = f'{context.domain.name}: {context.name}'
        c['id'] = f'{context.domain.dom_id}.{context.ent_id}'
        c['count'] = context.count
        contexts.append(c)
    conts = [cont for cont in contexts if cont['id'] not in ctracked]
    return htags[:10], mnames[:10], conts[:10]


# The Filtered Stream class
class LiveStream(AsyncStreamingClient):

    async def update_rules_from_twitter(self):
        rules = await self.get_rules()
        print('Rules: ', rules)
        channel_layer = get_channel_layer()
        await sync_to_async(set_rules_to_inactive)()
        try:
            for rule in rules[0]:
                rule = StreamRules(
                    id=rule.id,
                    value=rule.value,
                    tag=rule.tag,
                    active=True
                )
                await channel_layer.group_send(
                    'tweet',
                    {
                        "type": "rule",
                        "id": str(rule.id),
                        "filters": str(rule.value),
                        "tag": str(rule.tag)
                    }
                )
                await sync_to_async(rule.save)()
        except TypeError:
            pass

    async def on_response(self, response):
        if response.data:
            tweet = response.data
            matching_rules = response.matching_rules
            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                'tweet',
                {
                    "type": "tweet",
                    "id": str(tweet.id),
                    "filters": ', '.join([rule.tag for rule in matching_rules])
                }
            )
            await sync_to_async(add_tweet_to_db)(tweet)
            hashtags, mentions, contexts = await sync_to_async(get_10_popular_h_m_c)()
            await channel_layer.group_send(
                'tweet',
                {
                    "type": "hmc",
                    "hashtags": hashtags,
                    "mentions": mentions,
                    "contexts": contexts
                }
            )

        if response.includes:
            includes = response.includes
            if 'media' in includes.keys():
                for media in includes['media']:
                    m = Media(
                        media_key=media.media_key,
                        type=media.type,
                        url=media.url,
                        duration_ms=media.duration_ms,
                        height=media.height,
                        preview_image_url=media.preview_image_url,
                        width=media.width,
                        alt_text=media.alt_text
                    )
                    await sync_to_async(m.save)()
            if 'users' in includes.keys():
                for user in includes['users']:
                    u = User(
                        id=user.id,
                        name=user.name,
                        username=user.username,
                        created_at=user.created_at,
                        description=user.description,
                        location=user.location,
                        pinned_tweet_id=user.pinned_tweet_id,
                        profile_image_url=user.profile_image_url,
                        protected=user.protected,
                        url=user.url,
                        verified=user.verified
                    )
                    await sync_to_async(u.save)()

    async def on_errors(self, errors):
        print(errors)

    async def on_closed(self, resp):
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            'tweet',
            {
                "type": "status",
                "message": "Stream connection closed by Twitter"
            }
        )

    async def on_connect(self):
        channel_layer = get_channel_layer()
        print('Connected to Twitter')
        await channel_layer.group_send(
            'tweet',
            {
                "type": "status",
                "message": "Streaming"
            }
        )

    async def on_connection_error(self):
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            'tweet',
            {
                "type": "status",
                "message": "Stream connection has errored or timed out"
            }
        )

    async def on_disconnect(self):
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            'tweet',
            {
                "type": "status",
                "message": "Stream disconnected"
            }
        )

    async def on_request_error(self, status_code):
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            'tweet',
            {
                "type": "status",
                "message": f'Stream encountered HTTP Error: {status_code}'
            }
        )


class EngagementTracker:
    def __init__(self, bearer_token):
        self.tracking = False
        self.bearer_token = bearer_token

    async def engagement_update(self, starttime):
        tweetids = await sync_to_async(get_tracked_tweets)(starttime)
        client = AsyncClient(self.bearer_token)
        tweets = await client.get_tweets(tweetids, tweet_fields=['public_metrics'])
        timestamp = timezone.now()
        print(f"Engagement updated at {timestamp.strftime('%X')}")
        for tweet in tweets[0]:                                         # Probably inefficient
            await sync_to_async(update_metrics)(
                tweetid=tweet.id,
                timestamp=timestamp,
                retweet_count=tweet.data['public_metrics']['retweet_count'],
                reply_count=tweet.data['public_metrics']['reply_count'],
                like_count=tweet.data['public_metrics']['like_count'],
                quote_count=tweet.data['public_metrics']['quote_count']
            )
        results = await sync_to_async(get_tweet_metrics)(timestamp, tweetids)
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            'tweet',
            {
                "type": "tweetmetrics",
                "results": results
            }
        )

    async def periodic_update(self, __seconds: float, func, *args, **kwargs):
        while True:
            if not self.tracking:
                break
            await asyncio.gather(
                asyncio.sleep(__seconds),
                func(*args, **kwargs)
            )


def get_tweet_metrics(timestamp, tweetids):

    old = TweetMetrics.objects.filter(time__lte=timestamp-timedelta(minutes=4))
    old.delete()
    metrics = TweetMetrics.objects.all().order_by('tweetid', '-time')
    tweetdict = defaultdict(list)
    res = dict()
    res_sorted = dict()
    res['30'] = dict()
    res['60'] = dict()
    res['180'] = dict()
    tweetmetrics = dict()
    for metric in metrics:
        if metric.tweetid.id not in tweetids:
            continue
        tweetdict[metric.tweetid.id].append(metric)
    for tweet in tweetdict:
        tweetmetric = dict()
        if len(tweetdict[tweet]) < 2:
            continue
        if len(tweetdict[tweet]) >= 2:
            tweetmetric['30'] = metric_count(tweetdict[tweet][0])-metric_count(tweetdict[tweet][1])
        if len(tweetdict[tweet]) >= 3:
            tweetmetric['60'] = metric_count(tweetdict[tweet][0])-metric_count(tweetdict[tweet][2])
        if len(tweetdict[tweet]) >= 7:
            tweetmetric['180'] = metric_count(tweetdict[tweet][0])-metric_count(tweetdict[tweet][6])
        if len(tweetmetric) > 0:
            tweetmetrics[tweet] = tweetmetric
    for tweet in tweetmetrics:
        if tweetmetrics[tweet]['30'] > 0:
            res['30'][tweet] = tweetmetrics[tweet]['30']
        if '60' in tweetmetrics[tweet].keys():
            if tweetmetrics[tweet]['60'] > 0:
                res['60'][tweet] = tweetmetrics[tweet]['60']
        if '180' in tweetmetrics[tweet].keys():
            if tweetmetrics[tweet]['180'] > 0:
                res['180'][tweet] = tweetmetrics[tweet]['180']
    for interval in res:
        res_sorted[interval] = list()
        r = ({k: v for k, v in sorted(res[interval].items(), key=lambda item: item[1], reverse=True)})
        i = 0
        for kp in r:
            if i >= 5:
                break
            res_sorted[interval].append({'id': kp, 'count': r[kp]})
            i += 1

    return res_sorted


def metric_count(count):
    return count.retweet_count+count.reply_count+count.like_count+count.quote_count
