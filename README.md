# First, Verify

**First, Verify** is a research series on volatility markets, model construction, and the less glamorous work that should happen before and during strategy design.

The principle is simple:

> Verify the measurement first. Then test the phenomenon. Only then ask whether it can be traded.

This repository contains the public code accompanying articles in the series. Note that this is NOT the full research environment: only scripts relevant to published analyses are included here. I'm not planning to include live trading scripts, if the research leads to any. 

## Research approach

The broader project follows a few rules, partly influenced by my favourite writer, Nassim Nicholas Taleb:

1. **Falsification before explanation.**
   Establish that a phenomenon exists before constructing a theory around it.

2. **Ex-ante information only.**
   Predictors must have been observable before the outcome being studied.

3. **Assumptions stay visible.**
   Calendar conventions, settlement mechanics, filters, transaction costs, and data limitations are part of the model.

4. **Simple before complex.**
   Prefer transparent empirical tests over machinery that can hide fragile assumptions.

5. **Implementation matters.**
   A statistical relationship is not automatically a tradable edge.

## Data

The research uses publicly available Cboe historical VIX futures data.

Raw market data is **not redistributed in this repository**. Scripts may therefore require the user to obtain the relevant source data independently and configure the input path locally.

## Scope

This is not a trading system, signal service, or recommendation repository.

The code is published for research transparency and reproducibility alongside the written series.

## Disclaimer

Nothing in this repository constitutes investment advice or a recommendation to buy or sell any financial instrument.

I try to minimise dependence on fragile assumptions and rigorously check for hidden errors, but as a single researcher I may still miss things.
I would be very happy to receive corrections, stronger tests, and more creative ideas from you.
