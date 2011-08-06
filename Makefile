CPP = cpp
ARGS = -nostdinc -P -traditional-cpp -Ilayout

LAYOUT = layout/analytics.html layout/leftmenu.html layout/topmenu.html layout/footer.html layout/header.html layout/screencast.html
SCREENCASTS = screencasts/malware_euroview2011.html
PAGES = index.html contribute.html obtain.html publications.html screencasts.html $(SCREENCASTS)

%.html : %.html.in
	$(CPP) $(ARGS) $< $@

.PHONY: all

all: pages

layout/header.html: layout/analytics.html layout/leftmenu.html layout/topmenu.html

$(PAGES) : $(LAYOUT)

pages: $(PAGES)

clean:
	rm *.html layout/*.html
