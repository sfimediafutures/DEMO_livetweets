from django.db import models


class StreamRules(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    value = models.CharField(max_length=512)
    tag = models.CharField(max_length=255, default=None, null=True)
    active = models.BooleanField(default=None)


class Hashtag(models.Model):
    hashtag = models.CharField(max_length=280)
    count = models.IntegerField(default=0)

    def __str__(self):
        return self.hashtag


class Mention(models.Model):
    mention = models.CharField(max_length=280)
    count = models.IntegerField(default=0)

    def __str__(self):
        return self.mention


class ContextDomain(models.Model):
    dom_id = models.CharField(max_length=3, default='')
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class ContextEntity(models.Model):
    ent_id = models.CharField(max_length=30, default='')
    name = models.CharField(max_length=200)
    domain = models.ForeignKey(ContextDomain, on_delete=models.SET_NULL, null=True)
    count = models.IntegerField(default=0)

    def __str__(self):
        return self.name


class Tweet(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    text = models.CharField(max_length=512)
    # attachements = dict | None
    author_id = models.CharField(default=None, max_length=255)
    # context_annotations = list # Moved to the context field
    conversation_id = models.CharField(default=None, max_length=255)
    created_at = models.DateTimeField(default=None)
    # entities = dict | None # Split into the hashtags and mention fields
    # geo = dict | None
    in_reply_to_user_id = models.CharField(default=None, max_length=255)
    lang = models.CharField(default=None, max_length=255)
    # non_public_metrics = dict | None  # Only available for publishing user
    # organic_metrics = dict | None  # Only available for publishing user
    possibly_sensitive = models.BooleanField(default=None)
    # promoted_metrics = dict | None  # Only available for publishing user
    # public_metrics = dict | None  # Handled by the TweetMetrics model
    # referenced_tweets = list[ReferencedTweet] | None
    reply_settings = models.CharField(default=None, max_length=255)
    source = models.CharField(default=None, max_length=255)
    # withheld = dict | None  # Dict from JSON of the reason for a tweet being withheld
    hashtags = models.ManyToManyField(Hashtag)
    mentions = models.ManyToManyField(Mention)
    context = models.ManyToManyField(ContextEntity)

    def __str__(self):
        return self.id


class TweetMetrics(models.Model):
    tweetid = models.ForeignKey(Tweet, on_delete=models.CASCADE)
    time = models.DateTimeField()
    retweet_count = models.IntegerField()
    reply_count = models.IntegerField()
    like_count = models.IntegerField()
    quote_count = models.IntegerField()


class ReferencedTweet(models.Model):
    tweetid = models.CharField(max_length=255)
    type = models.CharField(max_length=255)


class User(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    name = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=None, null=True)
    description = models.CharField(default=None, max_length=255, null=True)
    # entities = dict | None
    location = models.CharField(default=None, max_length=255, null=True)
    pinned_tweet_id = models.CharField(default=None, max_length=255, null=True)
    profile_image_url = models.CharField(default=None, max_length=255, null=True)
    protected = models.BooleanField(default=None, null=True)
    # public_metrics = dict | None  # Handled by UserMetrics model
    url = models.CharField(default=None, max_length=255, null=True)
    verified = models.BooleanField(default=None, null=True)
    # withheld = dict | None  # Dict from JSON of the reason for a profile being withheld

    def __str__(self):
        return self.username


class UserMetrics(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    followers_count = models.IntegerField()
    following_count = models.IntegerField()
    tweet_count = models.IntegerField()
    listed_count = models.IntegerField()


class Media(models.Model):
    media_key = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    url = models.CharField(default=None, max_length=255, null=True)
    duration_ms = models.IntegerField(default=None, null=True)
    height = models.IntegerField(default=None, null=True)
    # non_public_metrics = dict | None  # Only available for publishing user
    # organic_metrics = dict | None  # Only available for publishing user
    preview_image_url = models.CharField(default=None, max_length=255, null=True)
    # promoted_metrics = dict | None  # Only available for publishing user
    # public_metrics = dict | None  # Handled by MediaMetrics model
    width = models.IntegerField(default=None, null=True)
    alt_text = models.CharField(default=None, max_length=255, null=True)

    def __str__(self):
        return self.media_key


class MediaMetrics(models.Model):
    media_key = models.ForeignKey(Media, on_delete=models.CASCADE)
    view_count = models.IntegerField()


class TrackedTweet(models.Model):
    tweetid = models.ForeignKey(Tweet, on_delete=models.CASCADE)
    created_at = models.DateTimeField()
    metrics_per_update = models.IntegerField()




