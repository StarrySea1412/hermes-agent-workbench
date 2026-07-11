FROM nginx:alpine

# Nginx 配置
COPY docker/nginx/default.conf /etc/nginx/conf.d/default.conf

# 前端构建产物
COPY ai-skill-app/dist /usr/share/nginx/html

EXPOSE 80
