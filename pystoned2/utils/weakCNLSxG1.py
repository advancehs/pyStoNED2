# import dependencies
from pyomo.environ import ConcreteModel, Set, Var, Objective, minimize, Constraint, log
from pyomo.core.expr.numvalue import NumericValue
import numpy as np
import pandas as pd
from ..constant import CET_ADDI, CET_MULT, FUN_PROD, FUN_COST, RTS_CRS, RTS_VRS, OPT_DEFAULT, OPT_LOCAL
from .tools import optimize_model


class weakCNLSxG1:
    """initial Group-VC-added weakCNLSx (weakCNLSx+G) model
    """

    def __init__(self, y, x, b, cutactive, cet=CET_ADDI, fun=FUN_PROD, rts=RTS_VRS):
        """weakCNLSx+G model

        Args:
            y (ndarray): output variable.
            x (ndarray): input variables.
            b (ndarray): undersiable variables.
            cutactive (float or ndarray): active concavity constraint.
            cet (String, optional): CET_ADDI (additive composite error term) or CET_MULT (multiplicative composite error term). Defaults to CET_ADDI.
            fun (String, optional): FUN_PROD (production frontier) or FUN_COST (cost frontier). Defaults to FUN_PROD.
            rts (String, optional): RTS_VRS (variable returns to scale) or RTS_CRS (constant returns to scale). Defaults to RTS_VRS.
        """
        # TODO(error/warning handling): Check the configuration of the model exist
        self.x = x
        self.y = y
        self.b = b
        self.cet = cet
        self.fun = fun
        self.rts = rts

        self.cutactive = cutactive

        # Initialize the CNLS model
        self.__model__ = ConcreteModel()

        # Initialize the sets
        self.__model__.I = Set(initialize=range(len(self.x))) #i行
        self.__model__.J = Set(initialize=range(len(self.y[0]))) #j个y
        self.__model__.L = Set(initialize=range(len(self.b[0])))  # l个b

        # Initialize the variables
        self.__model__.alpha = Var(self.__model__.I, doc='alpha')
        self.__model__.delta = Var(self.__model__.I,
                                  self.__model__.J,
                                  bounds=(0.0, None),
                                  doc='delta')
        self.__model__.gamma = Var(self.__model__.I,
                                   self.__model__.L,
                                   bounds=(0.0, None),
                                   doc='gamma')
        self.__model__.epsilon = Var(self.__model__.I, doc='residual')
        self.__model__.frontier = Var(self.__model__.I,
                                      bounds=(0.0, None),
                                      doc='estimated frontier')

        # Setup the objective function and constraints
        self.__model__.objective = Objective(rule=self.__objective_rule(),
                                             sense=minimize,
                                             doc='objective function')
        self.__model__.regression_rule = Constraint(self.__model__.I,
                                                    rule=self.__regression_rule(),
                                                    doc='regression equation')
        if self.cet == CET_MULT:
            self.__model__.log_rule = Constraint(self.__model__.I,
                                                 rule=self.__log_rule(),
                                                 doc='log-transformed regression equation')
        self.__model__.afriat_rule = Constraint(self.__model__.I,
                                                rule=self.__afriat_rule(),
                                                doc='elementary Afriat approach')
        self.__model__.disposability_rule = Constraint(self.__model__.I,
                                                        self.__model__.I,
                                                        rule=self.__disposability_rule(),
                                                        doc='weak disposibility')
        self.__model__.sweet_rule = Constraint(self.__model__.I,
                                               self.__model__.I,
                                               rule=self.__sweet_rule(),
                                               doc='sweet spot approach')

        # Optimize model
        self.optimization_status = 0
        self.problem_status = 0

    def optimize(self, email=OPT_LOCAL, solver=OPT_DEFAULT):
        """Optimize the function by requested method

        Args:
            email (string): The email address for remote optimization. It will optimize locally if OPT_LOCAL is given.
            solver (string): The solver chosen for optimization. It will optimize with default solver if OPT_DEFAULT is given.
        """
        # TODO(error/warning handling): Check problem status after optimization
        self.problem_status, self.optimization_status = optimize_model(
            self.__model__, email, self.cet, solver)

    def __objective_rule(self):
        """Return the proper objective function"""

        def objective_rule(model):
            return sum(model.epsilon[i] ** 2 for i in model.I)

        return objective_rule

    def __regression_rule(self):
        """Return the proper regression constraint"""
        if self.cet == CET_ADDI:
            if self.rts == RTS_VRS:

                def regression_rule(model, i):
                    return self.x[i] == - model.alpha[i] \
                        + sum(model.gamma[i, j] * self.y[i][j] for j in model.J) \
                        - sum(model.delta[i, l] * self.b[i][l] for l in model.L) \
                        - model.epsilon[i]

                return regression_rule
            elif self.rts == RTS_CRS:

                def regression_rule(model, i):
                    return self.x[i] == sum(model.gamma[i, j] * self.y[i][j] for j in model.J) \
                        - sum(model.delta[i, l] * self.b[i][l] for l in model.L) \
                        - model.epsilon[i]

                return regression_rule

        elif self.cet == CET_MULT:

            def regression_rule(model, i):
                return log(self.x[i]) == - log(model.frontier[i] + 1) \
                     - model.epsilon[i]

            return regression_rule

        raise ValueError("Undefined model parameters.")

    def __log_rule(self):
        """Return the proper log constraint"""
        if self.cet == CET_MULT:
            if self.rts == RTS_VRS:

                def log_rule(model, i):
                    return model.frontier[i] == model.alpha[i] - sum(
                        model.gamma[i, j] * self.y[i][j] for j in model.J) \
                            + sum(model.delta[i, l] * self.b[i][l] for l in model.L) - 1

                return log_rule
            elif self.rts == RTS_CRS:

                def log_rule(model, i):
                    return model.frontier[i] == - sum(
                        model.gamma[i, j] * self.y[i][j] for j in model.J) \
                            + sum(model.delta[i, l] * self.b[i][l] for l in model.L) - 1

                return log_rule

        raise ValueError("Undefined model parameters.")

    def __afriat_rule(self):
        """Return the proper elementary Afriat approach constraint"""
        if self.fun == FUN_PROD:
            __operator = NumericValue.__le__
        elif self.fun == FUN_COST:
            __operator = NumericValue.__ge__

        if self.rts == RTS_VRS:

            def afriat_rule(model, i):
                return __operator(
                    model.alpha[i] + sum(model.delta[i, l] * self.b[i][l]for l in model.L) \
                                   - sum(model.gamma[i, j] * self.y[i][j] for j in model.J),
                    model.alpha[self.__model__.I.nextw(i)] \
                           + sum(model.delta[self.__model__.I.nextw(i), l] * self.x[i][l]for l in model.L) \
                        - sum(model.gamma[self.__model__.I.nextw(i), j] * self.y[i][j] for j in model.J))

            return afriat_rule

        elif self.rts == RTS_CRS:
            def afriat_rule(model, i):
                return __operator(
                    sum(model.delta[i, l] * self.b[i][l]for l in model.L) \
                                   - sum(model.gamma[i, j] * self.y[i][j] for j in model.J),
                    sum(model.delta[self.__model__.I.nextw(i), l] * self.x[i][l]for l in model.L) \
                        - sum(model.gamma[self.__model__.I.nextw(i), j] * self.y[i][j] for j in model.J))

            return afriat_rule
        raise ValueError("Undefined model parameters.")

    def __disposability_rule(self):
        """Return the proper elementary weak disposability constraint"""
        if self.rts == RTS_VRS:
            def disposability_rule(model, i):
                return model.alpha[self.__model__.I.nextw(i)] \
                    + sum(self.x[i][j] for j in model.J)  >= 0
            return disposability_rule

        elif self.rts == RTS_CRS:
            def disposability_rule(model, i):
                return sum(self.x[i][j] for j in model.J)  >= 0
            return disposability_rule
        raise ValueError("Undefined model parameters.")


    def __sweet_rule(self ):
        """Return the proper sweet spot approach constraint"""
        if self.fun == FUN_PROD:
            __operator = NumericValue.__le__
        elif self.fun == FUN_COST:
            __operator = NumericValue.__ge__

        if self.rts == RTS_VRS:

            def sweet_rule(model, i, h):
                if self.cutactive[i][h]:
                    if i == h:
                        return Constraint.Skip
                    return __operator(model.alpha[i] \
                                      - sum(model.gamma[i, j] * self.y[i][j] for j in model.J) \
                                      + sum(model.delta[i, l] * self.b[i][l] for l in model.L),
                                      model.alpha[h] \
                                      - sum(model.gamma[h, j] * self.y[i][j] for j in model.J) \
                                      + sum(model.delta[h, l] * self.b[i][l] for l in model.L) )
                return Constraint.Skip

            return sweet_rule
        elif self.rts == RTS_CRS:

            def sweet_rule(model, i, h):
                if self.cutactive[i][h]:
                    if i == h:
                        return Constraint.Skip
                    return __operator(- sum(model.gamma[i, j] * self.y[i][j] for j in model.J) \
                                      + sum(model.delta[i, l] * self.b[i][l] for l in model.L),
                                      - sum(model.gamma[h, j] * self.y[i][j] for j in model.J) \
                                      + sum(model.delta[h, l] * self.b[i][l] for l in model.L) )
                return Constraint.Skip

            return sweet_rule

        raise ValueError("Undefined model parameters.")

    def get_alpha(self):
        """Return alpha value by array"""
        if self.optimization_status == 0:
            self.optimize()
        alpha = list(self.__model__.alpha[:].value)
        return np.asarray(alpha)

    def get_delta(self):
        """Return delta value by array"""
        if self.optimization_status == 0:
            self.optimize()
        delta = np.asarray([i + tuple([j]) for i, j in zip(list(self.__model__.delta),
                                                          list(self.__model__.delta[:, :].value))])
        delta = pd.DataFrame(delta, columns=['Name', 'Key', 'Value'])
        delta = delta.pivot(index='Name', columns='Key', values='Value')
        return delta.to_numpy()

    def get_gamma(self):
        """Return gamma value by array"""
        if self.optimization_status == 0:
            self.optimize()
        gamma = np.asarray([i + tuple([j]) for i, j in zip(list(self.__model__.gamma),
                                                           list(self.__model__.gamma[:, :].value))])
        gamma = pd.DataFrame(gamma, columns=['Name', 'Key', 'Value'])
        gamma = gamma.pivot(index='Name', columns='Key', values='Value')
        return gamma.to_numpy()