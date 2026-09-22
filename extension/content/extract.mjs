// Self-contained: Chromium serializes this function into an isolated content-script world.
export async function collectPage(maxComments = 100, selectedText = "") {
  try {
    const originalUrl = location.href;
    if (!["http:", "https:"].includes(location.protocol))
      throw new Error("仅支持普通 HTTP(S) 网页，请打开要保存的网页后重试");
    const host = location.hostname;
    const platform = ["xiaohongshu.com", "www.xiaohongshu.com"].includes(host)
      ? "xiaohongshu"
      : ["xiaoheihe.cn", "www.xiaoheihe.cn", "api.xiaoheihe.cn"].includes(host)
        ? "xiaoheihe"
        : "web";
    const clean = (value) => (value || "").replace(/\u0000/g, "").trim();
    const text = (node) => clean(node?.innerText || node?.textContent);
    const first = (root, selectors) =>
      selectors
        .flatMap((selector) => Array.from(root.querySelectorAll(selector)))
        .find((node) => visible(node));
    const visible = (node) =>
      node &&
      !!(
        node.getClientRects().length &&
        getComputedStyle(node).visibility !== "hidden"
      );
    const safeUrl = (value) => {
      if (!value) return null;
      try {
        const url = new URL(value, location.href);
        if (
          !["http:", "https:"].includes(url.protocol) ||
          url.username ||
          url.password
        )
          return null;
        if (url.port && !["80", "443"].includes(url.port)) return null;
        if (
          /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[|0\.|169\.254\.)/.test(
            url.hostname,
          ) ||
          /\.(local|internal|localhost)$/.test(url.hostname)
        )
          return null;
        return url.href;
      } catch {
        return null;
      }
    };
    const count = (value) => {
      const match = clean(value)
        .replace(/,/g, "")
        .match(/([\d.]+)\s*(万|千|亿|[wk])?/i);
      return match
        ? Math.min(
            2147483647,
            Math.floor(
              Number(match[1]) *
                ({ 万: 10000, 千: 1000, 亿: 1e8, w: 10000, k: 1000 }[
                  match[2]?.toLowerCase()
                ] || 1),
            ),
          ) || 0
        : 0;
    };
    const profiles = {
      xiaohongshu: {
        path: /\/(explore|discovery\/item)\/[a-zA-Z0-9]+/,
        root: [
          ".note-detail-mask .note-container",
          ".note-container",
          ".note-detail",
        ],
        title: ["#detail-title", ".title"],
        body: ["#detail-desc", ".desc"],
        author: [
          ".author-wrapper .username",
          ".author-wrapper .name",
          ".author .name",
        ],
        authorLink: [
          ".author-wrapper a[href*='/user/profile/']",
          ".author a[href*='/user/profile/']",
        ],
        comments:
          ".comments-container .comment-item, .comments-container .parent-comment",
        commentText: [".content .note-text", ".content", ".comment-content"],
        commentAuthor: [".author .name", ".user-name", ".name"],
        likes: [".like .count", ".like-wrapper .count"],
        replies: [".reply .count", ".reply-count"],
        total: [".comments-container .total"],
        end: [".comments-container .end-container"],
        scroll: [".note-scroller", ".comments-container"],
        more: [".comments-container .show-more"],
      },
      xiaoheihe: {
        path: /\/(app\/bbs\/link\/[^/]+|bbs\/app\/link\/web\/view)/,
        root: [".article-detail", ".post-detail", ".link-detail", "main"],
        title: [".article-title", ".post-title", ".link-title", "h1"],
        body: [".article-content", ".post-content", ".link-content"],
        author: [".author-name", ".user-info .username", ".author .name"],
        authorLink: [".author a[href]", ".user-info a[href]"],
        comments: ".comment-list .comment-item, .comments .comment-item",
        commentText: [".comment-content", ".content"],
        commentAuthor: [".user-name", ".author-name", ".username"],
        likes: [".like-count", ".like .count"],
        replies: [".reply-count"],
        total: [".comment-total", ".comments-count"],
        end: [".comments .no-more", ".comment-list .no-more"],
        scroll: [".comment-list", ".comments"],
        more: [".comment-list .load-more", ".comments .load-more"],
      },
    };
    const profile = profiles[platform];
    if (profile && !profile.path.test(location.pathname))
      throw new Error("请先打开要保存的帖子详情，再点击保存");
    const root = profile
      ? first(document, profile.root)
      : first(document, ["article", "main", "[role=main]", "body"]);
    if (!root)
      throw new Error("未找到帖子正文，请确认已登录并打开帖子详情，或更新扩展");
    const content = profile ? first(root, profile.body) : root;
    if (!content || !text(content))
      throw new Error("正文尚未加载，请等待页面显示内容后重新保存");
    const title = profile
      ? text(first(root, profile.title))
      : clean(document.title);
    if (!title) throw new Error("未找到标题，页面结构可能已变化，请更新扩展");
    const warnings = [];
    // Use DOM text only, excluding form controls, scripts, styles and hidden application state.
    const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        return parent?.closest(
          "script, style, noscript, template, input, textarea, select, button, nav, footer, [hidden], [aria-hidden=true]",
        ) || !visible(parent)
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT;
      },
    });
    const lines = [];
    while (walker.nextNode()) {
      const value = clean(walker.currentNode.textContent);
      if (value) lines.push(value);
    }
    const originalText = lines.join("\n");
    if (!originalText) throw new Error("未找到可见正文，请等待页面加载后重试");
    if (originalText.length > 8000000)
      throw new Error("页面文字过多，请缩小内容后保存");
    const selection = clean(selectedText || window.getSelection()?.toString());
    if (selection.length > 50000)
      throw new Error("选区超过 5 万字，请缩小选区后重试");
    const imageRoot = profile
      ? root.querySelector(
          ".media-container, .slider-container, .note-slider",
        ) || content
      : content;
    const images = [
      ...new Set(
        Array.from(imageRoot.querySelectorAll("img"))
          .map((img) => safeUrl(img.currentSrc || img.src || img.dataset.src))
          .filter(Boolean),
      ),
    ].slice(0, 1000);
    const author = profile
      ? text(first(root, profile.author))
      : clean(document.querySelector('meta[name="author"]')?.content);
    const authorUrl = profile
      ? safeUrl(first(root, profile.authorLink)?.getAttribute("href") || "")
      : null;
    const rawDate =
      first(root, ["time[datetime]"])?.getAttribute("datetime") ||
      document.querySelector('meta[property="article:published_time"]')
        ?.content;
    const date =
      rawDate &&
      /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(rawDate) &&
      !Number.isNaN(Date.parse(rawDate))
        ? new Date(rawDate).toISOString()
        : null;
    const comments = new Map();
    const limit = Math.max(0, Math.min(100, Number(maxComments) || 0));
    if (profile && limit) {
      const originalScroll = [window.scrollX, window.scrollY];
      const scroller = first(root, profile.scroll);
      const scrollTop = scroller?.scrollTop;
      const endTime = Date.now() + 14000;
      let unchanged = 0;
      let complete = false;
      try {
        while (Date.now() < endTime && comments.size < limit) {
          if (location.href !== originalUrl || !root.isConnected)
            throw new Error("页面已切换，请在目标帖子重新保存");
          const before = comments.size;
          for (const node of root.querySelectorAll(profile.comments)) {
            if (
              node.parentElement?.closest(profile.comments) ||
              node.closest(".sub-comments, .reply-list, .replies")
            )
              continue;
            const value = text(first(node, profile.commentText));
            if (!value || !visible(node)) continue;
            const name = text(first(node, profile.commentAuthor));
            const id = node.dataset.commentId || node.id || name + "\n" + value;
            if (!comments.has(id))
              comments.set(id, {
                author: name.slice(0, 500) || null,
                content: value.slice(0, 20000),
                likes: count(text(first(node, profile.likes))),
                replies: count(text(first(node, profile.replies))),
              });
            if (comments.size >= limit) break;
          }
          const totalText = text(first(root, profile.total));
          const total = totalText ? count(totalText) : null;
          complete =
            profile.end.some((selector) =>
              visible(root.querySelector(selector)),
            ) ||
            (total !== null && total === comments.size);
          if (complete || comments.size >= limit) break;
          unchanged = comments.size === before ? unchanged + 1 : 0;
          if (unchanged >= 3) break;
          const more = first(root, profile.more);
          if (
            visible(more) &&
            !more.closest(".sub-comments, .reply-list, .replies") &&
            /加载更多|查看更多评论|更多评论/.test(text(more))
          )
            more.click();
          if (scroller && scroller.scrollHeight > scroller.clientHeight)
            scroller.scrollTop = scroller.scrollHeight;
          else
            root
              .querySelector(profile.comments)
              ?.parentElement?.scrollIntoView({ block: "end" });
          await new Promise((resolve) => setTimeout(resolve, 700));
        }
      } finally {
        if (scroller) scroller.scrollTop = scrollTop;
        window.scrollTo(...originalScroll);
      }
      if (!complete)
        warnings.push(
          `已读取 ${comments.size} 条页面顶层评论；受采集上限、加载时间和页面可见性限制，可能不完整。可展开评论后重新保存。`,
        );
    }
    if (profile && !limit) warnings.push("已按设置关闭评论采集");
    if (location.href !== originalUrl)
      throw new Error("页面已切换，请重新保存当前帖子");
    return {
      url: originalUrl,
      payload: {
        title: title.slice(0, 2000),
        text: originalText,
        author: author.slice(0, 500) || null,
        author_url: authorUrl,
        published_at: date,
        images,
        comments: [...comments.values()],
        selection: selection || null,
        capture_warnings: warnings,
      },
    };
  } catch (error) {
    return { error: error.message || "页面读取失败，请刷新页面后重试" };
  }
}
