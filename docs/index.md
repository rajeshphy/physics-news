---
layout: default
title: Physics Brief
---

<h1>Physics Brief</h1>

<ul class="post-list">
  {% for post in site.posts %}
    <li>
      <time datetime="{{ post.date | date_to_xmlschema }}">
        {{ post.date | date: "%Y-%m-%d" }}
      </time>
      <a href="{{ post.url | relative_url }}">{{ post.summary | default: post.title }}</a>
    </li>
  {% else %}
    <li class="no-posts">No briefs yet.</li>
  {% endfor %}
</ul>
