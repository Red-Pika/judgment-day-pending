.PHONY: test evidence run
test:
	python3 -m unittest discover -s tests -t . -v
evidence:
	python3 -m scripts.generate_evidence
run:
	python3 -m opsguard.app
