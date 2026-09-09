.PHONY: build run

build:
	@python3 -c "from PIL import Image; print('Pillow ready')"

run:
	python3 rasterizer.py $(file)
