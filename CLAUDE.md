# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Macro-beans is a Python-based repository for swing trading analysis and investigations. The project focuses on identifying opportunistic trading opportunities through ad-hoc analyses and scripts, with results presented via Streamlit apps.

## Environment Setup

This project uses Conda for environment management:

```bash
# Create the conda environment
conda env create -f environment.yml

# Activate the environment
conda activate macro-beans
```

The project uses Python 3.11 as specified in `environment.yml`.

## Repository Structure

- `scripts/` - Ad-hoc investigation scripts for trading opportunities
- `src/` - Source code for reusable components and utilities
- `docs/` - Documentation files

## Development Workflow

Since this is a project for ad-hoc trading analyses:
- Scripts in `scripts/` are expected to be exploratory and investigation-focused
- Streamlit apps should be used to present analysis results
- Each analysis should be self-contained and focused on specific trading opportunities

## Key Technologies

- **Language**: Python 3.11
- **Presentation**: Streamlit (for visualizing trading analysis results)
- **Environment**: Conda
