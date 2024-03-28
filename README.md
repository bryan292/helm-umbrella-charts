# Helm Umbrella Charts

## Overview
This repository contains a collection of Helm umbrella charts. Umbrella charts are a way to package multiple Helm charts together for easier deployment and management.

## Current Applications
AWS Load Balance Controller
The AWS Load Balancer Controller is essential for automating and managing load balancers in AWS. It simplifies configuration, supports advanced features like dynamic scaling and traffic routing, and integrates with other AWS services, enhancing application performance and infrastructure reliability.

## Cert-Manager
Cert-Manager is vital in a Kubernetes cluster to automate the management of SSL/TLS certificates. It ensures secure communication between services and automates the certificate lifecycle. We have integrated it with Letsencrypt.

## Cluster Autoscaler
The Cluster Autoscaler maintains the correct number of nodes to handle workloads efficiently. It automatically adjusts the size of the cluster based on current needs, scaling up when there's a demand for more resources and scaling down when resources are underutilized. This ensures optimal resource usage and cost-effectiveness.

## demo-app
The idea of the demo-app chart is to receive, via the values file, the information for a GitHub repository that also contains a helm chart. This demo-app will create the CRD for the repository and the Helm Release.

## External-DNS
It synchronizes exposed Kubernetes services and Ingresses with DNS providers, making the services reachable with human-friendly domain names. This simplifies service discovery and enhances the accessibility of applications running on the cluster, this is implemented with AWS Route 53.

## weave-gitops
A friendly UI useful to force syncronization of Flux sources and Helm Releases.