package services

import (
	"errors"
	"strings"

	"gorm.io/gorm"
)

// maxNumberRetries 是建立報價單／訂單時，因單號撞到唯一索引而重試的次數上限。
// 單號以「當日筆數 + 1」產生，並行建立時可能撞號；重試時序號逐次加一。
const maxNumberRetries = 5

// isDuplicateKey 判斷錯誤是否為唯一索引衝突（GORM 翻譯後的錯誤或 PostgreSQL 23505）。
func isDuplicateKey(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, gorm.ErrDuplicatedKey) {
		return true
	}
	msg := err.Error()
	return strings.Contains(msg, "23505") || strings.Contains(msg, "duplicate key")
}

// createWithRetry 以 generate 產生單號、assign 填入、create 寫入；撞號時換下一個序號重試。
func createWithRetry(generate func(offset int64) (string, error), assign func(string), create func() error) error {
	var err error
	for attempt := range maxNumberRetries {
		number, genErr := generate(int64(attempt))
		if genErr != nil {
			return genErr
		}
		assign(number)
		if err = create(); err == nil {
			return nil
		}
		if !isDuplicateKey(err) {
			return err
		}
	}
	return err
}
