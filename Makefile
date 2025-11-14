.PHONY: run-app

# To run the Streamlit app, first activate your conda environment:
# conda activate replay-tool
run-app:
	export PYTHONPATH=$(PYTHONPATH):$(pwd) && streamlit run src/replay/app.py