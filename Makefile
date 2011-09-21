CPP = cpp
ARGS = -nostdinc -P -traditional-cpp -Ilayout

LAYOUT = layout/analytics.html layout/leftmenu.html layout/topmenu.html layout/footer.html layout/header.html layout/screencast.html
PAGES = $(shell find *.html.in presentations publications -name '*.html.in' | sed 's/.html.in/.html/g')

%.html : %.html.in
	$(CPP) $(ARGS) $< $@

.PHONY: all

all: pages

layout/header.html: layout/analytics.html layout/leftmenu.html layout/topmenu.html

$(PAGES) : $(LAYOUT)

pages: $(PAGES)

clean:
	rm *.html layout/*.html
