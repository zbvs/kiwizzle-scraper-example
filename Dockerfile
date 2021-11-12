#zbvs/kiwizzle:kiwizzle-scraper-1.0.0
FROM python:3.9.4-buster

#install base dependencies
RUN apt-get update && apt-get install -y \
    fonts-liberation libappindicator3-1 libasound2 libatk-bridge2.0-0 \
    libnspr4 libnss3 lsb-release xdg-utils libxss1 libdbus-glib-1-2 \
    curl unzip wget \
    xvfb libgbm1

#install font
RUN apt-get install -y \
        fonts-ipafont-gothic fonts-ipafont-mincho \
        ttf-wqy-microhei fonts-wqy-microhei       \
        fonts-tlwg-loma fonts-tlwg-loma-otf

# RUN CHROMEDRIVER_VERSION=`curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE` && \
#     wget https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip && \
#     unzip chromedriver_linux64.zip -d /usr/bin && \
#     chmod +x /usr/bin/chromedriver && \
#     rm chromedriver_linux64.zip


# RUN CHROME_SETUP=google-chrome.deb && \
#     wget -O $CHROME_SETUP "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb" && \
#     dpkg -i $CHROME_SETUP && \
#     apt-get install -y -f && \
#     rm $CHROME_SETUP

  
ADD ./kiwizzle-scraper/ /app
WORKDIR /app
RUN CHROME_SETUP=/app/chrome/google-chrome-stable_current_amd64.deb && \
    dpkg -i $CHROME_SETUP && \
    apt-get install -y -f

RUN pip3 install -r requirements.txt
ENTRYPOINT ["bash","scraper-entry.sh"]