"""Deployable ML estimators for a specified positive-quantity relationship."""

from collections import defaultdict
import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.utils.validation import check_is_fitted

from features.tabular_regression import feature_frame, feature_names, preprocessor


class QuantityMedianRegressor(RegressorMixin, BaseEstimator):
    def __init__(self, feature_schema, quantity_feature, group_feature):
        self.feature_schema=feature_schema
        self.quantity_feature=quantity_feature
        self.group_feature=group_feature

    def _frame(self, X):
        rows=X.to_dict('records') if hasattr(X,'to_dict') else X
        frame=feature_frame(rows,self.feature_schema)
        if (frame[self.quantity_feature]<=0).any():
            raise ValueError('quantity normalization requires strictly positive quantities')
        return frame

    def fit(self, X, y, sample_weight=None):
        frame=self._frame(X);target=np.asarray(y,dtype=float)
        if len(target)!=len(frame) or not np.isfinite(target).all() or (target<0).any():
            raise ValueError('target must be aligned, finite and nonnegative')
        self.feature_names_in_=np.asarray(feature_names(self.feature_schema),dtype=object)
        rate=target/frame[self.quantity_feature].to_numpy(dtype=float)
        grouped=defaultdict(list)
        for category,value in zip(frame[self.group_feature],rate):grouped[category].append(value)
        self.group_medians_={key:float(np.median(values)) for key,values in grouped.items()}
        self.global_median_=float(np.median(rate))
        return self

    def predict(self, X):
        check_is_fitted(self,['group_medians_','global_median_'])
        frame=self._frame(X)
        return np.asarray([quantity*self.group_medians_.get(category,self.global_median_)
            for quantity,category in zip(frame[self.quantity_feature],frame[self.group_feature])],dtype=float)


class QuantityNormalizedRidge(RegressorMixin, BaseEstimator):
    def __init__(self, feature_schema, quantity_feature, alpha=1.0):
        self.feature_schema=feature_schema
        self.quantity_feature=quantity_feature
        self.alpha=alpha

    def _frame(self,X):
        rows=X.to_dict('records') if hasattr(X,'to_dict') else X
        frame=feature_frame(rows,self.feature_schema)
        if (frame[self.quantity_feature]<=0).any():raise ValueError('quantity normalization requires positive quantities')
        return frame

    def fit(self,X,y,sample_weight=None):
        frame=self._frame(X);target=np.asarray(y,dtype=float)
        if len(target)!=len(frame) or not np.isfinite(target).all() or (target<0).any():raise ValueError('invalid target')
        self.feature_names_in_=np.asarray(feature_names(self.feature_schema),dtype=object)
        normalized=target/frame[self.quantity_feature].to_numpy(dtype=float)
        self.regressor_=Pipeline([('features',preprocessor(self.feature_schema)),('regressor',Ridge(alpha=self.alpha,solver='lsqr'))])
        self.regressor_.fit(frame,normalized,regressor__sample_weight=sample_weight)
        return self

    def predict(self,X):
        check_is_fitted(self,'regressor_');frame=self._frame(X)
        rates=self.regressor_.predict(frame)
        if not np.isfinite(rates).all():raise ValueError('nonfinite normalized estimate')
        return np.maximum(0,rates)*frame[self.quantity_feature].to_numpy(dtype=float)
