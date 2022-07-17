from django.contrib import admin

from .models import *

admin.site.register(Tweet)
admin.site.register(TweetMetrics)
admin.site.register(ReferencedTweet)
admin.site.register(User)
admin.site.register(UserMetrics)
admin.site.register(Media)
admin.site.register(MediaMetrics)
admin.site.register(StreamRules)
admin.site.register(Hashtag)
admin.site.register(Mention)
admin.site.register(ContextEntity)
admin.site.register(ContextDomain)
admin.site.register(TrackedTweet)

# Register your models here.
