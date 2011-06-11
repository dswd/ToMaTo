CPP = cpp
ARGS = -nostdinc -P -traditional-cpp -Ilayout

LAYOUT = layout/leftmenu.html layout/topmenu.html layout/footer.html layout/header.html
PAGES = index.html contribute.html obtain.html publications.html

%.html : %.html.in
	$(CPP) $(ARGS) $< $@

.PHONY: all

all: pages

layout/header.html: layout/leftmenu.html layout/topmenu.html

$(PAGES) : $(LAYOUT)

pages: $(PAGES)

clean:
	rm *.html layout/*.html
