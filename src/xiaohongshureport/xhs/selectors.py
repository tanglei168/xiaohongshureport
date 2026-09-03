"""Centralized selectors ordered from stable attributes to class fallbacks."""

NOTE_LINK = 'a[href*="/explore/"], a[href*="/discovery/item/"]'
ACCOUNT_LINK = 'a[href*="/user/profile/"]'
NOTE_CARD_TITLE = '[data-testid="note-card-title"], h3, h2, .title span, .title'
NOTE_CARD_LIKE = '[data-testid="note-card-like"], [aria-label*="点赞"], .like-wrapper .count'
NOTE_CARD_IMAGE = "img"
VIDEO = "video"
SCROLL_CONTAINER = '[data-testid="feed-scroll-container"], .feeds-page'

ACCOUNT_NICKNAME = (
    '[data-testid="user-name"]',
    '[data-testid="nickname"]',
    'meta[property="og:title"]',
    ".user-name",
    ".username",
)
ACCOUNT_BIO = ('[data-testid="user-bio"]', '[data-testid="description"]', ".user-desc")
ACCOUNT_AVATAR = (
    '[data-testid="user-avatar"] img',
    'meta[property="og:image"]',
    'img[alt*="头像"]',
)
ACCOUNT_STATS = ('[data-testid="user-stats"]', ".user-interactions", ".data-info")

NOTE_TITLE = (
    '[data-testid="note-title"]',
    'meta[property="og:title"]',
    "h1",
    ".title",
)
NOTE_CONTENT = (
    '[data-testid="note-content"]',
    'meta[property="og:description"]',
    "article",
    ".desc",
)
NOTE_AUTHOR = ('[data-testid="note-author"]', ACCOUNT_LINK)
NOTE_PUBLISH_TIME = ("time[datetime]", '[data-testid="publish-time"]', ".date")
NOTE_LIKE = ('[data-testid="like-count"]', '[aria-label*="点赞"]', ".like-wrapper .count")
NOTE_COLLECT = ('[data-testid="collect-count"]', '[aria-label*="收藏"]', ".collect-wrapper .count")
NOTE_COMMENT = ('[data-testid="comment-count"]', '[aria-label*="评论"]', ".chat-wrapper .count")
NOTE_SHARE = ('[data-testid="share-count"]', '[aria-label*="分享"]', ".share-wrapper .count")
NOTE_HASHTAG = ('a[href*="/search_result?keyword="]', '[data-testid="hashtag"]')
NOTE_COVER = ('meta[property="og:image"]', '[data-testid="note-cover"] img')

LOGIN_MARKERS = ("text=扫码登录", "text=登录后推荐更懂你的笔记", "text=手机号登录")
