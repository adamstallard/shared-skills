# Sequencer

Builds on: inquisitor (adamstallard/shared-skills#25)

## Why

Agents work out by hand, in each session, which of a repository's open
issues and pull requests to specify, build, review and merge first, and
nothing keeps that order current as the work changes.

## What Changes

- A new skill, `sequencer`, that computes and publishes the order of a
  repository's open work.
