---
layout: page
title: Tournaments
permalink: /tournaments/
---

{% assign events=site.data.tournaments %}

| {% for column in events[0] %}{{ column[0] }} | {% endfor %} 
| {% for column in events[0] %} --- | {% endfor %}
{% for row in events %} | {% for cell in row %}{{ cell[1] }} | {% endfor %}
{% endfor %}