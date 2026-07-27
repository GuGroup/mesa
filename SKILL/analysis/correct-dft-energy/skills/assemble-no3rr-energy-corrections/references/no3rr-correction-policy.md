# NO3RR correction and interpretation policy

## 1. HNO3 molecular error

Define a method-specific correction:

\[
\delta_{HNO_3}=\Delta_fG_{exp}^{\circ}(HNO_3)-\Delta_fG_{DFT}^{\circ}(HNO_3).
\]

Apply it only to the HNO3 reference used to construct the nitrate adsorption scale. A value reported for HNO3 is not a correction for HNO2, NO2, NO, N2O4, or adsorbed NOx species.

## 2. HNO3-to-nitrate transfer cycle

The skill stores either one direct value or two explicit components:

\[
HNO_3(g)\rightarrow HNO_3(l)
\]

\[
HNO_3(l)\rightarrow NO_3^-(aq)+H^+(aq).
\]

At nonzero pH and non-unit activities:

\[
\Delta G_{transfer}(pH)=\Delta G_{transfer}^{\circ}
-k_BT\ln(10)\,pH
+k_BT\ln(a_{NO_3^-}/a_{HNO_3}).
\]

The original `+0.392 eV` conversion is therefore a pH-0 standard-state consequence of a `-0.392 eV` transfer free energy, not a universal pH-independent constant.

## 3. Potential dependence

For an adsorbate state with `n_pair` proton-electron pairs and `n_e,net = n_pair - 1` net electrons consumed, the electrochemical cumulative energy is:

\[
\Delta G_{EC}=\Delta G_{neutral}-\Delta G_{transfer}
-n_{e,net}(\mu_{H^++e^-}-\tfrac12G_{H_2}).
\]

On RHE:

\[
\mu_{H^++e^-}-\tfrac12G_{H_2}=-eU_{RHE}.
\]

On SHE:

\[
\mu_{H^++e^-}-\tfrac12G_{H_2}=-eU_{SHE}-k_BT\ln(10)pH.
\]

This formulation gives `-1` net electron for nitrate adsorption, `+1` for ordinary reduction PCET steps, and `+8` for the overall nitrate-to-NH3 reaction.

## 4. Limiting potential

For every electron-consuming step:

\[
\Delta G_i(U)=\Delta G_i(0)+n_{e,i}eU.
\]

The cathodic limiting potential is the most restrictive threshold:

\[
U_L=\min_i[-\Delta G_i(0)/(n_{e,i}e)].
\]

The overall equilibrium potential is:

\[
U_{eq}=-\Delta G_{overall}(0)/(8e).
\]

The bounded thermodynamic overpotential is `U_eq - U_L`. Electron-releasing adsorption and potential-independent desorption are reported separately because a PCET limiting potential alone may not make the entire pathway downhill.

## 5. Model boundary

This helper supports one nitrogen atom ending as NH3. N2/N2O pathways, NO3-to-NH2OH terminal products, explicit NH4+, coupled C-N chemistry, and direct aqueous-ion DFT require a more general reaction-network input rather than changing constants in this script.
